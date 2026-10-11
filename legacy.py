from condition import *
from os.path import splitext, dirname, abspath
import os
import sys
os.environ["PATH"] = dirname(abspath(sys.argv[0])) + os.pathsep + os.environ["PATH"]
import mpv
import random
import time
import subprocess
import re
import threading
import array
import math
from concurrent.futures import ThreadPoolExecutor
from config import settings

# Cache of playback positions (in ms) keyed by absolute file path.
# Used by sync-enabled goalhorns to preserve playback position
# across different ConditionPlayer instances with the same filename,
# without sharing a single MediaPlayer object (which caused concurrency bugs).
_position_cache = {}

# Cache of loudness measurements keyed by absolute file path.
# Stores (mean_db, max_db, loud_part_db_or_None, pcm_mean_db_or_None) per file.
# mean_db / max_db come from ffmpeg volumedetect (whole-track RMS and peak).
# loud_part_db is the RMS of the loudest portion of the track (top N% of
# 1-second windows), computed only for chants so that a chant with a long
# quiet section and a short loud section is normalized based on its loud
# part rather than being over-boosted by the dragged-down mean.
# pcm_mean_db is the whole-track RMS from the same PCM decode as loud_part_db,
# used for the log line so both numbers are consistent (volumedetect's mean
# uses a different internal decoder path and can differ by a fraction of a dB).
# Populated lazily by analyze_loudness when a song is played,
# or proactively by start_background_analysis after loading.
_loudness_cache = {}

# Track files currently being analyzed to avoid duplicate volumedetect calls.
_loudness_pending = set()
_loudness_pending_lock = threading.Lock()

# Track files that have already been logged so we don't repeat the analysis
# summary on every play() call (gain is recomputed from cached measurements
# each time, but the log line should appear only once per file).
_loudness_logged = set()

def _run_volumedetect(fullpath):
   """Run ffmpeg volumedetect and return (mean_db, max_db) or (None, None) on failure."""
   kwargs = dict(capture_output=True, text=True, errors="replace", timeout=30)
   if os.name == "nt":
      kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
   result = subprocess.run(
      ["ffmpeg", "-vn", "-i", fullpath, "-af", "volumedetect", "-f", "null", "-"],
      **kwargs
   )
   stderr = result.stderr
   mean_match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", stderr)
   max_match = re.search(r"max_volume:\s*(-?[\d.]+)\s*dB", stderr)
   if not mean_match or not max_match:
      return None, None
   return float(mean_match.group(1)), float(max_match.group(1))

def _run_loud_part_analysis(fullpath, sample_rate=44100, window_sec=1.0):
   """Decode audio to mono PCM and compute the RMS of the loudest portion.
   Returns (loud_part_db, pcm_mean_db) in dBFS, or (None, None) on failure.
   Also returns pcm_mean_db — the whole-track RMS computed from the same PCM
   decode — so that both numbers come from identical samples and loud_part_db
   is guaranteed >= pcm_mean_db (unlike volumedetect's mean, which uses a
   different internal decoder path and can differ by a fraction of a dB).
   Splits the track into 1-second windows, computes RMS for each to rank them,
   then pools all samples from the loudest N% of windows (N from
   chant_loud_part_percent) and computes a single RMS over those pooled samples.
   Uses s16le PCM output (signed 16-bit little-endian) which is supported by
   the minimized ffmpeg build (pcm_s16le encoder + s16le muxer + pipe protocol)."""
   loud_percent = settings.config.get("chant_loud_part_percent", 20)
   kwargs = dict(capture_output=True, timeout=60)
   if os.name == "nt":
      kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
   result = subprocess.run(
      ["ffmpeg", "-vn", "-i", fullpath, "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-"],
      **kwargs
   )
   pcm = result.stdout
   if not pcm:
      return None, None
   # s16le: signed 16-bit little-endian samples
   raw = array.array('h')
   raw.frombytes(pcm)
   n = len(raw)
   if n == 0:
      return None, None
   window_size = max(1, int(sample_rate * window_sec))
   # compute (sum_of_squares, sample_count) per 1-second window
   windows = []
   total_sum_sq_all = 0
   for i in range(0, n, window_size):
      chunk = raw[i:i+window_size]
      sum_sq = sum(s * s for s in chunk)
      windows.append((sum_sq, len(chunk)))
      total_sum_sq_all += sum_sq
   if not windows:
      return None, None
   # whole-track RMS from the same PCM (for consistent comparison)
   if n == 0 or total_sum_sq_all <= 0:
      return None, None
   pcm_mean_rms = math.sqrt(total_sum_sq_all / n) / 32768.0
   if pcm_mean_rms <= 0:
      return None, None
   pcm_mean_db = 20 * math.log10(pcm_mean_rms)
   # sort by RMS (sum_sq / count) descending, take top loud_percent% of windows
   windows.sort(key=lambda w: w[0] / w[1], reverse=True)
   n_loud = max(1, int(len(windows) * loud_percent / 100))
   # pool all samples from the loudest windows and compute RMS over them
   total_sum_sq = sum(w[0] for w in windows[:n_loud])
   total_count = sum(w[1] for w in windows[:n_loud])
   if total_count == 0 or total_sum_sq <= 0:
      return None, pcm_mean_db
   loud_part_rms = math.sqrt(total_sum_sq / total_count) / 32768.0
   if loud_part_rms <= 0:
      return None, pcm_mean_db
   return 20 * math.log10(loud_part_rms), pcm_mean_db

def _ensure_volumedetect(fullpath):
   """Ensure ffmpeg volumedetect measurements are cached for fullpath.
   Returns (mean_db, max_db, loud_part_db_or_None, pcm_mean_db_or_None) or None on failure.
   Thread-safe: uses _loudness_pending to prevent duplicate ffmpeg calls."""
   # fast path: already cached
   cached = _loudness_cache.get(fullpath)
   if cached is not None:
      return cached if cached[0] is not None else None
   # claim this file or wait for another thread to finish it
   with _loudness_pending_lock:
      cached = _loudness_cache.get(fullpath)
      if cached is not None:
         return cached if cached[0] is not None else None
      if fullpath in _loudness_pending:
         pending = True
      else:
         _loudness_pending.add(fullpath)
         pending = False
   if pending:
      # another thread is analyzing this file; wait for it
      while fullpath not in _loudness_cache:
         time.sleep(0.01)
      cached = _loudness_cache.get(fullpath)
      if cached is None or cached[0] is None:
         return None
      return cached
   # we claimed the file — run volumedetect
   try:
      mean_db, max_db = _run_volumedetect(fullpath)
      if mean_db is None:
         print("   Could not parse volumedetect output for {}".format(fullpath))
         _loudness_cache[fullpath] = (None, None, None, None)
         return None
      _loudness_cache[fullpath] = (mean_db, max_db, None, None)
      return _loudness_cache[fullpath]
   except FileNotFoundError:
      print("   ffmpeg not found, skipping normalization for {}".format(fullpath))
      _loudness_cache[fullpath] = (None, None, None, None)
      return None
   except Exception as e:
      print("   Error analyzing loudness for {}: {}".format(fullpath, e))
      if fullpath not in _loudness_cache:
         _loudness_cache[fullpath] = (None, None, None, None)
      return None
   finally:
      with _loudness_pending_lock:
         _loudness_pending.discard(fullpath)

def _ensure_measurements(fullpath, need_loud_part=False):
   """Ensure loudness measurements are cached for fullpath.
   If need_loud_part is True, also ensure the loud-part RMS is computed.
   Returns (mean_db, max_db, loud_part_db_or_None, pcm_mean_db_or_None) or None on failure.
   Phase 1 (volumedetect) is protected by _loudness_pending to avoid duplicate
   ffmpeg calls. Phase 2 (loud-part PCM decode) runs without the lock — if two
   threads request it simultaneously, both will decode, but the result is
   deterministic so the duplicate write is harmless."""
   # Phase 1: ensure volumedetect measurements are cached
   cached = _ensure_volumedetect(fullpath)
   if cached is None:
      return None
   mean_db, max_db, loud_part_db, pcm_mean_db = cached
   # Phase 2: ensure loud-part RMS is cached (chants only)
   if need_loud_part and loud_part_db is None:
      loud_part_db, pcm_mean_db = _run_loud_part_analysis(fullpath)
      _loudness_cache[fullpath] = (mean_db, max_db, loud_part_db, pcm_mean_db)
   return _loudness_cache[fullpath]

def analyze_loudness(filepath, target_db, is_chant=False):
   """Analyze audio loudness and calculate gain needed to reach target_db.
   For chants, uses the RMS of the loudest portion of the track (top N% of
   1-second windows, per chant_loud_part_percent) as the reference instead
   of the whole-track mean, so that a chant with a long quiet section and a
   short loud section is normalized based on its loud part rather than being
   over-boosted. Goalhorns, anthems, and victory anthems use the whole-track
   mean as before (unchanged behavior).
   Returns (gain_db, needs_limiter) or (None, False) on failure.
   A limiter is needed when the full gain would cause peak clipping.
   Thread-safe: uses a lock to prevent duplicate ffmpeg calls for the same file."""
   fullpath = abspath(filepath)
   measurements = _ensure_measurements(fullpath, need_loud_part=is_chant)
   if measurements is None:
      return None, False
   mean_db, max_db, loud_part_db, pcm_mean_db = measurements
   # choose reference: loud-part RMS for chants, whole-track mean for others
   if is_chant and loud_part_db is not None:
      reference = loud_part_db
      # use pcm_mean_db (from the same PCM decode) for the log line so both
      # numbers are consistent; volumedetect's mean uses a different decoder
      # path and can differ by a fraction of a dB
      display_mean = pcm_mean_db if pcm_mean_db is not None else mean_db
   else:
      reference = mean_db
      display_mean = mean_db
   gain = target_db - reference
   needs_limiter = (max_db + gain) > 0.0
   # log once per file so the streamer can see what was decided
   if fullpath not in _loudness_logged:
      _loudness_logged.add(fullpath)
      if is_chant and loud_part_db is not None:
         print("   {} has loud-part volume of {:.1f} dB (mean: {:.1f} dB) and peak of {:.1f} dB, target is {:.1f} dB; applying {:.1f} dB gain{}.".format(
            basename(fullpath), loud_part_db, display_mean, max_db, target_db, gain,
            " with limiter" if needs_limiter else ""))
      elif needs_limiter:
         print("   {} has mean volume of {:.1f} dB and peak of {:.1f} dB, target is {:.1f} dB; applying {:.1f} dB gain with limiter.".format(
            basename(fullpath), mean_db, max_db, target_db, gain))
      else:
         print("   {} has mean volume of {:.1f} dB and peak of {:.1f} dB, target is {:.1f} dB; applying {:.1f} dB gain.".format(
            basename(fullpath), mean_db, max_db, target_db, gain))
   return (gain, needs_limiter)

def start_background_analysis(filepaths, target_db, chant_paths=None, anthem_paths=None, victory_paths=None):
   """Start analyzing loudness for all files in a background thread pool.
   Non-blocking: returns immediately. Results populate _loudness_cache.
   If a file is played before its analysis completes, play() will wait for it.
   chant_paths: iterable of paths for chant files, which receive an additional
   loud-part RMS analysis pass so normalization targets their loud portion.
   anthem_paths / victory_paths: iterables for anthem and victory anthem files,
   used only for priority ordering (anthems are played first after loading, so
   they are analyzed before goalhorns, which are analyzed before chants, which
   are analyzed before victory anthems)."""
   chant_set = set(abspath(f) for f in (chant_paths or []))
   anthem_set = set(abspath(f) for f in (anthem_paths or []))
   victory_set = set(abspath(f) for f in (victory_paths or []))
   # priority: anthem=0, goalhorn=1, chant=2, victory=3
   def priority(f):
      if f in anthem_set:
         return 0
      if f in victory_set:
         return 3
      if f in chant_set:
         return 2
      return 1
   unique = set(abspath(f) for f in filepaths if isfile(abspath(f)))
   to_analyze = []
   for f in unique:
      if f in _loudness_pending:
         continue
      cached = _loudness_cache.get(f)
      if cached is None:
         to_analyze.append((f, f in chant_set))
      elif cached[0] is None:
         continue  # previous analysis failed, don't retry
      elif f in chant_set and cached[2] is None:
         to_analyze.append((f, True))  # need loud-part pass
   if not to_analyze:
      return
   # sort by priority so higher-priority files (anthems first) are submitted
   # to the thread pool before lower-priority ones; with 4 workers the first
   # batch picks up the highest-priority files
   to_analyze.sort(key=lambda item: priority(item[0]))
   print("Starting background loudness analysis for {} file(s)...".format(len(to_analyze)))
   def worker():
      with ThreadPoolExecutor(max_workers=min(4, len(to_analyze))) as executor:
         list(executor.map(lambda args: analyze_loudness(args[0], target_db, is_chant=args[1]), to_analyze))
   thread = threading.Thread(target=worker, daemon=True)
   thread.start()

class ConditionList:
   def __init__(self, pname = "NOPLAYER", tname = "NOTEAM", data = [], songname = "New Song", home = True, runInstructions = True):
      self.pname = pname
      self.tname = tname
      self.home = home
      self.songname = songname
      self.conditions = []
      self.instructions = []
      self.disabled = False
      self.startTime = 0
      self.event = None
      self.endType = "loop"
      self.pauseType = "continue"
      for tokenStr in data:
         tokens = processTokens(tokenStr)
         condition = buildCondition(tokens, pname=self.pname, tname=self.tname, home=self.home)
         if condition.isInstruction():
            self.instructions.append(condition)
         else:
            self.conditions.append(condition)
      self.all = self.conditions + self.instructions
      if runInstructions:
         self.instruct()

   def __str__(self):
      output = "{}".format(basename(self.songname))
      for condition in self.conditions:
         output = output + ";" + str(condition)
      for instruction in self.instructions:
         output = output + ";" + str(instruction)
      return output

   def __repr__ (self):
      pname = self.pname
      tname = self.tname
      data = str(self).split(";")[1:]
      songname = self.songname
      home = self.home
      output = "ConditionList(pname={},tname={},data={},songname={},home={})"
      return output.format(pname,tname,data,songname,home)

   def __len__ (self):
      return len(self.all)

   def __iter__ (self):
      return self.all.__iter__()

   def __getitem__ (self, key):
      return self.all[key]

   def __setitem__ (self, key, value):
      temp = self.all[key]
      if temp.isInstruction():
         index = self.instructions.index(temp)
         self.instructions[index] = value
      else:
         index = self.conditions.index(temp)
         self.conditions[index] = value
      # insert new value where it was
      self.all[key] = value

   def instruct (self):
      for instruction in self.instructions:
         if instruction.allowUnloaded():
            print("Preparing {} instruction".format(instruction))
            instruction.prep(self)

   def append (self, item):
      self.all.append(item)
      if item.isInstruction():
         self.instructions.append(item)
      else:
         self.conditions.append(item)

   def disable (self):
      self.disabled = True

   def pop (self, index = 0):
      item = self.all.pop(index)
      if item.isInstruction():
         self.instructions.remove(item)
      else:
         self.conditions.remove(item)
      return item

   def check (self, gamestate):
      if self.disabled:
         raise UnloadSong
      for condition in self.conditions:
         print("Checking {}".format(condition))
         if not condition.check(gamestate):
            return False
      return True

   def toYML (self):
      # with no conditions, simply return song name
      if len(self.all) == 0:
         return basename(self.songname)
      # otherwise, store filename in dict
      output = {}
      output["filename"] = basename(self.songname)
      output["conditions"] = []
      for item in self.conditions:
         output["conditions"].append(item.toYML())
      output["instructions"] = []
      for item in self.instructions:
         output["instructions"].append(item.toYML())
      return output

class ConditionPlayer (ConditionList):
   def __init__ (self, pname, tname, data, songname, home, type = "goalhorn", sync = False, normalize = True):
      ConditionList.__init__(self,pname,tname,data,songname,home,False)
      self.type = type
      self.isGoalhorn = type=="goalhorn"
      self.sync = sync
      # per-team normalize opt-out; when False, loudness analysis is skipped
      # and a baseline of 0 dB is used (boost still applies to louder-marked tracks)
      self.normalize = normalize
      self.song = self.loadsong(songname)
      self.fade = None
      self.startTime = 0
      self.customSpeed = False
      self.firstPlay = True
      self.randomise = False
      self.warcry = False
      self.pauseType = "continue"
      self.instructionsStart = []
      self.instructionsPause = []
      self.instructionsEnd = []
      self.maxVolume = 100
      self.normalize_gain = None
      self.louder = False
      self.boostValue = 0
      # repetition settings; may be changed by instructions
      norepeat = set(["victory","chant"])
      self.repeat = (pname not in norepeat)
      # append and prepare the instructions to this object
      self.appendInstructions()
      self.instruct()
      # songs with a set start time require manual looping so that it loops back to the set time
      setStartTime = any(isinstance(instruction, StartInstruction) for instruction in self.instructionsStart)
      self.manualLoop = setStartTime
      self._configureLooping()

   def _configureLooping (self):
      # configure native looping for repeat-enabled songs;
      # called both at init and after reloadSong since each player is separate
      if self.repeat and self.event is None and isinstance(self.song, mpv.MPV) and not self.manualLoop:
         self.song.loop_file = "inf"

   def appendInstructions (self):
      for instruction in self.instructions:
         print("Appending {} instruction".format(instruction))
         instruction.append(self)

   def instruct (self):
      for instruction in self.instructions:
         print("Preparing {} instruction".format(instruction))
         instruction.prep(self)

   def loadsong(self, filename):
      print("Attempting to load "+filename)
      fullpath = abspath(filename)

      # if song cannot be found, return error message instead of MediaPlayer
      # reason is to have rigdio check for all missing files before raising exception
      if not isfile(fullpath):
         return basename(fullpath) + " not found."
      # vid=False prevents video tracks; pause=True keeps file paused until play()
      # keep_open=True prevents idle mode after EOF (matches ended state behavior)
      player = mpv.MPV(vid=False, pause=True, keep_open=True, volume_max=220)
      player.loadfile(fullpath)
      return player

   def reloadSong (self):
      self.firstPlay = True
      # clear saved position since we're resetting to the beginning
      _position_cache.pop(abspath(self.songname), None)
      self.song = self.loadsong(self.songname)
      self._configureLooping()
      self.instruct()

   def applyNormalizeFilter (self):
      """Recompute and apply the normalization audio filter to the current mpv
      player based on the current normalize flag. Called lazily by play() before
      playback, and also safe to call on a currently playing song so that a
      normalize toggle takes effect live instead of only on the next play().
      No-op when normalization is disabled globally or the song isn't loaded."""
      if not settings.config["normalize_volume"] or not isinstance(self.song, mpv.MPV):
         return
      if self.normalize:
         fullpath = abspath(self.songname)
         gain, needs_limiter = analyze_loudness(fullpath, settings.level["target"], is_chant=(self.type == "chant"))
         # re-check the flag after the (potentially blocking) analysis: the user
         # may have toggled normalize back off while we waited, in which case
         # applying the gain now would override the freshly applied 0 dB baseline
         if not self.normalize:
            return
         if gain is not None:
            if self.louder:
               total_gain = gain + self.boostValue
               self.song.af = "volume={:.1f}dB,alimiter=limit=0.95".format(total_gain)
            elif needs_limiter:
               self.song.af = "volume={:.1f}dB,alimiter=limit=0.95".format(gain)
            else:
               self.song.af = "volume={:.1f}dB".format(gain)
            self.normalize_gain = gain
         else:
            # analysis failed: clear any previously applied filter so we don't
            # keep playing at a stale gain (e.g. after toggling normalize off)
            self.normalize_gain = None
            self.song.af = ""
      else:
         # normalization opted out for this team: baseline 0 dB
         # boost still applies on top of the baseline for louder-marked tracks
         self.normalize_gain = 0
         if self.louder and self.boostValue != 0:
            self.song.af = "volume={:.1f}dB,alimiter=limit=0.95".format(float(self.boostValue))
         else:
            # clear any previously applied normalized filter so the track plays
            # at its native 0 dB baseline
            self.song.af = ""

   def play (self):
      if self.fade is not None:
         print("Song played quickly after pause, cancelling fade.")
         thread = self.fade
         self.fade = None
         thread.join()
      # apply normalization gain as audio filter before playback (lazy — only when actually played)
      self.applyNormalizeFilter()
      self.song.pause = False
      self.song.volume = self._toMpvVolume(self.maxVolume)
      # restore saved playback position for sync-enabled goalhorns
      if self.sync and self.isGoalhorn and not self.warcry and isinstance(self.song, mpv.MPV):
         fullpath = abspath(self.songname)
         if fullpath in _position_cache:
            self.song.time_pos = _position_cache[fullpath] / 1000.0
      if self.firstPlay:
         for instruction in self.instructionsStart:
            instruction.run(self)
         self.firstPlay = False

   def _toMpvVolume (self, sliderValue):
      # Convert slider value (0-200, 100=unity) to mpv's cubic volume scale.
      # mpv applies gain as (volume/100)^3, so to get a desired dB gain:
      #   gain = 10^(dB/20), volume = 100 * gain^(1/3) = 100 * 10^(dB/60)
      # Slider 0→-20dB (quiet), 100→0dB (unity), 200→+20dB (10x boost)
      if sliderValue <= 0:
         return 0
      if sliderValue <= 100:
         dB = -20 * (1 - sliderValue / 100)
      else:
         dB = 20 * (sliderValue - 100) / 100
      return 100 * 10 ** (dB / 60)

   def adjustVolume (self, value):
      self.maxVolume = int(value)
      self.song.volume = self._toMpvVolume(self.maxVolume)

   def pause (self, fade=None):
      # save playback position for sync-enabled goalhorns before pausing
      if self.sync and self.isGoalhorn and not self.warcry and isinstance(self.song, mpv.MPV):
         pos = self.song.time_pos
         if pos is not None:
            _position_cache[abspath(self.songname)] = int(pos * 1000)
      if fade is None:
         fade = self.type in settings.fade and settings.fade[self.type]
      # don't fade out if the song has already ended (e.g. advance/warcry)
      if fade and not self.song.eof_reached:
         print("Fading out {}.".format(self.songname))
         self.fade = threading.Thread(target=self.fadeOut)
         self.fade.start()
      else:
         for instruction in self.instructionsPause:
            instruction.run(self)
         self.song.pause = True
         if self.song.eof_reached:
            self.reloadSong()

   def onEnd (self, callback):
      @self.song.event_callback('end-file')
      def _handler(event):
         callback()

   def fadeOut (self):
      # save playback position for sync-enabled goalhorns before fading out
      if self.sync and self.isGoalhorn and not self.warcry and isinstance(self.song, mpv.MPV):
         pos = self.song.time_pos
         if pos is not None:
            _position_cache[abspath(self.songname)] = int(pos * 1000)
      i = 100
      mpvVol = self._toMpvVolume(self.maxVolume)
      while i > 0:
         if self.fade == None:
            break
         volume = int(mpvVol * i/100)
         self.song.volume = volume
         sleep(settings.fade["time"]/100)
         i -= 1
      for instruction in self.instructionsPause:
         instruction.run(self)
      self.song.pause = True
      if self.song.eof_reached:
         self.reloadSong()
      self.song.volume = self._toMpvVolume(self.maxVolume)
      self.fade = None

   def disable (self):
      self.song.command("stop")
      super().disable()

class PlayerManager:
   def __init__ (self, clists, home, game, master):
      # song information
      self.clists = clists
      self.home = home
      self.game = game
      # playerbutton information
      self.master = master
      # derived information
      self.song = None
      self.lastSong = None
      self.endChecker = None
      self.pname = clists[0].pname
      self.futureVolume = None
      self.warcry = True

   def __iter__ (self):
      for x in self.clists:
         yield x

   def adjustVolume (self, value):
      if self.song is not None:
         self.song.adjustVolume(value)
      self.futureVolume = value

   def getSong (self, song = None, skip = None):
      if song is not None:
         for clist in self.clists:
            if song == clist:
               return clist
      # if warcry mode is active, check for randomised warcry songs
      if self.warcry:
         warcrySongs = [c for c in self.clists if c.warcry and c is not skip]
         if warcrySongs and all(c.randomise for c in warcrySongs):
            return random.choice(warcrySongs)
      # iterate over songs with while loop
      i = 0
      while i < len(self.clists):
         # skip the song that just ended (advance instruction)
         if self.clists[i] is skip:
            i += 1
            continue
         # try to check the condition list
         try:
            checked = self.clists[i].check(self.game)
         # if a song will no longer be played, check will raise UnloadSong
         except UnloadSong:
            # disable the ConditionListPlayer, closing the song file
            self.clists[i].disable()
            # deleted
            del self.clists[i]
            # do not increment i, self.clists[i] is now the next song; continue
            continue
         # if randomise is true, check if all other songs have randomise true as well
         # do not count warcry songs
         if self.clists[i].randomise and not self.clists[i].warcry:
            f, randomSong = 0, True
            while f < len(self.clists):
               # if one of them is false and they're not a warcry, do not play a random song
               if not self.clists[f].randomise and not self.clists[f].warcry and self.clists[i].pname == self.clists[f].pname:
                  randomSong = False
                  break
               f += 1
            if randomSong:
               # copy the entire song list of that team
               x, randomList = 0, self.clists.copy()
               while x < len(randomList):
                  # traverse through and remove all songs that are not associated with the player clicked
                  # remove all warcry songs from the list as well
                  if self.clists[i].pname != randomList[x].pname or randomList[x].warcry:
                     randomList.pop(x)
                  else:
                     x += 1
               # reset the warcry variable so that warcry will play again when button is pressed
               self.warcry = True
               # return a randomly chosen song from the modified copied list
               return random.choice(randomList)
         # if conditions were met
         if checked:
            # if warcry is enabled, play the first song found, warcry included
            if self.warcry:
               return self.clists[i]
            # if a warcry has been played, play the first non-warcry song found
            else:
               if not self.clists[i].warcry:
                  # reset the warcry variable so that warcry will play again when button is pressed
                  self.warcry = True
                  return self.clists[i]
         # if the song didn't succeed, move to the next
         i += 1
      # fallback: if no valid song was found, play the first non-warcry song
      # that isn't the skipped one (advance instruction)
      if skip is not None:
         i = 0
         while i < len(self.clists):
            if self.clists[i] is skip:
               i += 1
               continue
            if not self.clists[i].warcry:
               self.warcry = True
               return self.clists[i]
            i += 1
         # final fallback: play the skipped song itself
         self.warcry = True
         return skip
      # if no song was found, return nothing
      return None

   def playSong (self, song = None, skip = None):
      # don't play multiple songs at once
      self.pauseSong()
      # get the song to play
      self.song = self.getSong(song, skip)
      # if volume was stored, update it
      if self.futureVolume is not None:
         self.song.adjustVolume(self.futureVolume)
      # check if no song was found
      if self.song is None:
         raise SongNotFound(self.pname)
      # log song
      print("Playing",self.song.songname)
      # a returnable value for whether this is the first time this song is played
      self.firstTime = self.song.firstPlay
      # play the song
      self.song.play()
      # start blinking if the playing song is louder-marked
      if hasattr(self.song, 'louder') and self.song.louder:
         frame = self.master.frame
         if hasattr(frame, 'hasLouder') and frame.hasLouder:
            frame.startBlinking()
      # start the end checker instruction thread
      if len(self.song.instructionsEnd) > 0 or (self.song.repeat and self.song.manualLoop):
         self.endChecker = threading.Thread(target=self.checkEnd)
         self.endChecker.start()
      # remove any data specific to this goal
      self.game.clearButtonFlags()
      # if the song is the victory anthem and not a warcry, start victory song duration timer
      if self.clists[0].pname == "victory" and not self.song.warcry:
         self.master.timer.retrieveSongInfo()

      # check if user has enabled write to title.log function
      if not self.song.warcry and settings.config["write_song_title_log"] != 0:
         global titleThread
         global titleCheck
         # if title timer thread already exists,
         # kill it and wait for it to die before creating a new one
         if titleCheck:
            titleCheck = False
            titleThread.join()
         titleThread = threading.Thread(target=self.writeTitleLog)
         titleThread.start()

      return self.firstTime

   def pauseSong (self):
      if self.song is not None:
         # stop blinking when a louder-marked song is paused
         frame = self.master.frame
         if hasattr(frame, 'hasLouder') and frame.hasLouder:
            frame.stopBlinking()
         # clear end checker thread to prevent continuous running while paused
         self.endChecker = None
         # log pause
         print("Pausing",self.song.songname)
         # pause the song
         self.song.pause()
         # clear self.song
         self.lastSong = self.song
         self.song = None

   def checkEnd (self):
      while self.endChecker is not None:
         if self.song.song.eof_reached:
            if len(self.song.instructionsEnd) > 0:
               for instruction in self.song.instructionsEnd:
                  instruction.run(self)
               break

            if self.song.repeat and self.song.manualLoop:
               self.song.song.time_pos = 0
               sleep(0.05)
               self.song.song.pause = False
               self.song.song.volume = self.song._toMpvVolume(self.song.maxVolume)
               for instruction in self.song.instructionsStart:
                  instruction.run(self.song)
               continue
         time.sleep(0.01)

   # if the song is currently playing or has been played, reset it
   def resetLastPlayed (self):
      if self.lastSong is not None or self.song is not None:
         self.pauseSong()
         self.lastSong.song.command("stop")
         self.lastSong.reloadSong()

   # in-place reset: pauses any playing song and seeks all songs back to the start
   # without reloading the physical files
   def reset (self):
      if self.song is not None:
         self.pauseSong()
      # full reset: seek every song to its start, clear cached playback positions,
      # and reset first-play state so start instructions run again on next play
      for clist in self.clists:
         _position_cache.pop(abspath(clist.songname), None)
         if hasattr(clist, 'firstPlay'):
            clist.firstPlay = True
         if hasattr(clist, 'song') and isinstance(clist.song, mpv.MPV):
            clist.song.time_pos = 0
      self.lastSong = None
      self.warcry = True

   # capture pre-play state so undo can restore it (playback position + warcry flag)
   def snapshot (self):
      return {
         'warcry': self.warcry,
         'songs': [
            (c, _position_cache.get(abspath(c.songname)), getattr(c, 'firstPlay', None))
            for c in self.clists
         ],
      }

   # restore pre-play state captured by snapshot()
   def restore (self, snapshot):
      self.warcry = snapshot['warcry']
      for c, pos, firstPlay in snapshot['songs']:
         fullpath = abspath(c.songname)
         if pos is None:
            _position_cache.pop(fullpath, None)
            # no cache entry to restore from on next play, so reset the mpv
            # player's position directly (otherwise it resumes from where it
            # was paused, since play() only sets time_pos from the cache)
            if hasattr(c, 'song') and isinstance(c.song, mpv.MPV):
               c.song.time_pos = 0
         else:
            _position_cache[fullpath] = pos
         if hasattr(c, 'firstPlay') and firstPlay is not None:
            c.firstPlay = firstPlay

   # writes currently playing song's details to title.log, clearing it after a set amount of time
   def writeTitleLog (self):
      print("Write title timer thread started.")
      global titleThread
      global titleCheck
      titleCheck = True
      # sleep delay needed for mpv to properly retrieve metadata
      sleep(1)
      # exit thread if it has been interrupted early
      if titleThread is None or not titleCheck:
         print("Write title timer thread ended early.")
         titleThread = None
         titleThread = False
         return

      # get metadata title and artist
      metadata = self.song.song.metadata or {}
      title = metadata.get("title")
      artist = metadata.get("artist")
      # music note to signify it's music or something (idk, it was requested)
      text = "♪ "
      # add artist details first if it's available
      if (artist is not None):
         text += artist + " — "
      try:
         # if a song doesn't have a metadata title, it returns the full filename including its path
         # hence it needs to be stripped before adding it to text
         if isfile(title):
            text += splitext(basename(title))[0]
         else:
            text += title
         # utf-8 encoding for weeb characters
         with open("title.log", 'w', encoding='utf8') as file:
            file.write(text)
      # if title could not be written in for some reason, use the filename instead
      except:
         path = self.song.song.path or ""
         text += splitext(basename(path))[0]
         with open("title.log", 'w', encoding='utf8') as file:
            file.write(text)

      timerStart = time.time()
      timeout = settings.config["write_song_title_log"]
      while titleThread is not None:
         # exit loop if thread has been interrupted, song has ended, or timer has run out
         # (-1 means keep the title visible for as long as the song is playing)
         if (
            not titleCheck or self.song is None or
            self.song.song.eof_reached or
            (timeout > 0 and (time.time() - timerStart) > timeout)
         ):
            break
         time.sleep(0.01)

      # clear title.log and exit thread
      print("Write title timer thread ended.")
      with open("title.log", 'w') as file:
         file.write("")
      titleThread = None
      titleCheck = False

# global variables for the title timer thread
# required as they need to be accessed across different PlayerManager instances
titleThread = None
titleCheck = False
