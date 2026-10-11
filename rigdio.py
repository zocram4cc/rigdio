import sys
import threading
from os.path import isfile, join, abspath, splitext

from tkinter import *
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

from config import genConfig, openConfig, applyDarkMode, applyLightMode, settings

from condition import MatchCondition
from rigparse import parse as parseLegacy
from gamestate import GameState
from songgui import *
from version import rigdio_version as version
from rigdj_util import setMaxWidth
from rigdio_util import volumeColor, sliderToDb, combineVolume
from event import EventController
import chantswindow as cWin
import legacy
import settingswindow
from webserver import start_webserver

from logger import startLog
if __name__ == '__main__':
   # allow/forbid rigdio to write to log depending on user's configs
   if settings.config["write_to_log"]:
      startLog("rigdio.log")
   # create a title.log file that will contain the current song's title/filename
   if settings.config["write_song_title_log"] != 0:
      open("title.log", 'w').close()
   print("rigdio {}".format(version))

class ScoreWidget (Frame):
   def __init__ (self, master, game):
      Frame.__init__(self,master)
      self.game = game
      # home/away team name labels
      self.homeName = StringVar()
      self.awayName = StringVar()
      self.updateLabels()
      Label(self, textvariable=self.homeName, font="-weight bold").grid(row=0,column=0)
      Label(self, text="vs.", font="-weight bold").grid(row=0,column=1)
      Label(self, textvariable=self.awayName, font="-weight bold").grid(row=0,column=2)
      # score tracker
      self.homeScore = IntVar()
      self.awayScore = IntVar()
      self.updateScore()
      Label(self, textvariable=self.homeScore).grid(row=1,column=0)
      Label(self, text="-").grid(row=1,column=1)
      Label(self, textvariable=self.awayScore).grid(row=1,column=2)

   def updateLabels (self):
      self.homeName.set("/{}/".format(self.game.home_name))
      self.awayName.set("/{}/".format(self.game.away_name))

   def updateScore (self):
      self.homeScore.set(self.game.home_score)
      self.awayScore.set(self.game.away_score)

class Rigdio (Frame):
   def __init__ (self, master):
      Frame.__init__(self, master)
      self.game = GameState(instance=self)
      self.home = None
      self.away = None
      # store the .4ccm file path for each slot so the team can be reloaded
      # (e.g. when the streamer toggles normalization after load)
      self.homeFile = None
      self.awayFile = None
      self.masterVolumeValue = 100
      # chants volume slider value — dB offset on top of master when normalize
      # is enabled, or the direct chant volume when normalize is disabled
      self.chantsVolumeValue = 100
      # flag to prevent recursive slider syncing between main window and chants window
      self._syncingChantsVolume = False
      # UI colour palette
      self.colours = settings.darkColours if settings.config["dark_mode_enabled"] else settings.lightColours
      # file menu
      homeButtons = Frame(self)
      Button(homeButtons, text="Load Home Team", command=self.loadFile, bg=self.colours["home"]).pack(fill=X)
      Button(homeButtons, text="Reset", command=self.resetTeam, bg=self.colours["reset"]).pack()
      homeButtons.grid(row=0, column=0)
      awayButtons = Frame(self)
      Button(awayButtons, text="Load Away Team", command=lambda: self.loadFile(False), bg=self.colours["away"]).pack(fill=X)
      Button(awayButtons, text="Reset", command=lambda: self.resetTeam(False), bg=self.colours["reset"]).pack()
      awayButtons.grid(row=0, column=2)
      # per-team normalize toggle buttons (only when global normalize is enabled)
      # shown below the reset buttons with a gap; disabled until a team is loaded
      self.normalizeButtons = {}
      if settings.config["normalize_volume"]:
         # small gap then the toggle button, in each team's button column
         Frame(homeButtons, height=8).pack()
         self.homeNormalizeBtn = Button(homeButtons, text="Normalize: Yes", command=lambda: self.toggleNormalize(True), bg=self.colours["normalize"], state=DISABLED)
         self.homeNormalizeBtn.pack(fill=X)
         self.normalizeButtons[True] = self.homeNormalizeBtn
         Frame(awayButtons, height=8).pack()
         self.awayNormalizeBtn = Button(awayButtons, text="Normalize: Yes", command=lambda: self.toggleNormalize(False), bg=self.colours["normalize"], state=DISABLED)
         self.awayNormalizeBtn.pack(fill=X)
         self.normalizeButtons[False] = self.awayNormalizeBtn
      # score widget
      self.scoreWidget = ScoreWidget(self, self.game)
      self.game.widget = self.scoreWidget
      self.scoreWidget.grid(row=0, column=1)
      # game type selector
      self.initGameTypeMenu().grid(row=1,column=1)
      # other stuff for the middle column, like playback speed slider and chants
      self.middleStuff = Frame(self)
      self.initMiddleStuff().grid(row=2,column=1)
      # used for the chaoshorn
      self.nuke = False
      # events
      self.events = EventController()
      if settings.config["webserver_enabled"]:
         start_webserver(self, settings.config["webserver_port"])
      # blank space
      Label(self, text=None).grid(row=3, column=1)
      # undo (temporary)
      Button(self, text="Undo Last Goal", command=self.game.undoLast, bg=self.colours["reset"]).grid(row=4, column=1)
      # blank gap then settings button
      Label(self, text=None).grid(row=5, column=1)
      Button(self, text="Settings", command=self.openSettings, bg=self.colours["normalize"]).grid(row=6, column=1)

   def initGameTypeMenu (self):
      gameTypeMenu = Frame(self)
      gametypes = MatchCondition.types
      Label(gameTypeMenu, text="Match Type").pack()
      gametype = StringVar()
      gametype.set(settings.match)
      self.game.gametype = gametype.get().lower()
      menu = OptionMenu(gameTypeMenu, gametype, *gametypes, command=self.changeGameType)
      setMaxWidth(gametypes,menu)
      menu.pack()
      return gameTypeMenu

   def changeGameType (self, option):
      self.game.gametype = option.lower()

   def initMiddleStuff (self):
      row = 0
      # chaos horn
      Label(self.middleStuff, text=None).grid(row=row, columnspan=2); row += 1
      self.chaosHorn = Button(self.middleStuff, text="Chaoshorn", command=self.goNuclear, bg="#ee4b2b")
      self.chaosHorn.grid(row=row, columnspan=2); row += 1
      self.killChaos = Button(self.middleStuff, text="Kill Chaoshorn", command=self.stopNuclear, bg=self.colours["kill"])
      self.killChaos.grid(row=row, columnspan=2); row += 1
      Label(self.middleStuff, text=None).grid(row=row, columnspan=2); row += 1
      # universal playback speed slider
      Label(self.middleStuff, text="Playback Speed").grid(row=row, columnspan=2); row += 1
      self.playbackSpeedLabel = Label(self.middleStuff, text="1.00x")
      self.playbackSpeedLabel.grid(row=row, columnspan=2); row += 1
      self.playbackSpeedMenu = Scale(self.middleStuff, from_=0.25, to=4.00, orient=HORIZONTAL, command=self._playbackSpeedCommand, resolution=0.25, showvalue=0, digits=3)
      self.playbackSpeedMenu.set(1.00)
      self.playbackSpeedMenu.grid(row=row, columnspan=2); row += 1
      Label(self.middleStuff, text=None).grid(row=row, columnspan=2); row += 1
      # master volume slider (only shown when normalize_volume is enabled)
      if settings.config["normalize_volume"]:
         Label(self.middleStuff, text="Master Volume").grid(row=row, columnspan=2); row += 1
         self.masterVolumeLabel = Label(self.middleStuff, text="+0 dB")
         self.masterVolumeLabel.grid(row=row, columnspan=2); row += 1
         self.masterVolume = Scale(self.middleStuff, from_=0, to=200, orient=HORIZONTAL, command=self.adjustMasterVolume, showvalue=0, troughcolor='#c8c8c8', bd=0, highlightthickness=0)
         self.masterVolume.set(100)
         self.masterVolume.configure(bg=volumeColor(100), activebackground=volumeColor(100))
         self.masterVolume.grid(row=row, columnspan=2); row += 1
         # gap between master and chants volume sliders
         Label(self.middleStuff, text=None).grid(row=row, columnspan=2); row += 1
      else:
         self.masterVolume = None
         self.masterVolumeLabel = None
      # chants volume slider — always shown.
      # When normalize is enabled this is a dB offset on top of master volume;
      # when normalize is disabled this is the direct chant volume control.
      Label(self.middleStuff, text="Chants Volume").grid(row=row, columnspan=2); row += 1
      self.chantsVolumeLabel = Label(self.middleStuff, text="+0 dB")
      self.chantsVolumeLabel.grid(row=row, columnspan=2); row += 1
      self.chantsVolume = Scale(self.middleStuff, from_=0, to=200, orient=HORIZONTAL, command=self.setChantsVolume, showvalue=0, troughcolor='#c8c8c8', bd=0, highlightthickness=0)
      self.chantsVolume.set(100)
      self.chantsVolume.configure(bg=volumeColor(100), activebackground=volumeColor(100))
      self.chantsVolume.grid(row=row, columnspan=2); row += 1
      # creates chants window and manager
      self.chantswindow = None
      self.chantsManager = cWin.ChantsManager(self.chantswindow, self)
      # manual chant controls
      Label(self.middleStuff, text=None).grid(row=row, columnspan=2); row += 1
      Button(self.middleStuff, text="Manual Chants", command=self.chant_window).grid(row=row, columnspan=2); row += 1
      # random chant buttons accessible from the main window
      self.randomHome = cWin.ChantsButton(self.middleStuff, self.chantsManager, None, "Random", True, True)
      self.randomHome.playButton.grid(row=row, column=0)
      self.randomAway = cWin.ChantsButton(self.middleStuff, self.chantsManager, None, "Random", False, True)
      self.randomAway.playButton.grid(row=row, column=1)
      self._randomButtonRow = row
      row += 1
      # stop chant early button
      self.stopEarlyButton = Button(self.middleStuff, text="Stop Chant Early", command=self.chantsManager.endThread, bg=self.colours["stop"])
      self.stopEarlyButton.grid(row=row, columnspan=2); row += 1
      return self.middleStuff

   def goNuclear(self):
      confirm = messagebox.askyesnocancel("Are you sure you want to do this?",
      """Chaoshorn will play all the player buttons (including the Anthem and VA) that are currently loaded at the same time. Do you still want to go the nuclear option?""", icon='warning')
      if not confirm or self.nuke:
         return
      else:
         if self.home is not None:
            self.home.goNuclear()
         if self.away is not None:
            self.away.goNuclear()
         self.nuke = True

   def stopNuclear(self):
      if self.nuke:
         if self.home is not None:
            self.home.stopNuclear()
         if self.away is not None:
            self.away.stopNuclear()
         self.nuke = False

   def _playbackSpeedCommand (self, value):
      self.playbackSpeedLabel.configure(text="{:.2f}x".format(float(value)))

   # used to disable the use of the playback speed slider when a song is playing, to make it obvious what the current playback speed is
   def disablePlaybackSpeedSlider (self, disable):
      if self.playbackSpeedMenu is not None:
         self.playbackSpeedMenu["state"] = DISABLED if disable else NORMAL
         self.playbackSpeedMenu["fg"] = 'grey' if disable else self.colours["fg"]
         if disable:
            # sync label to the slider's current position
            self.playbackSpeedLabel.configure(text="{:.2f}x".format(self.playbackSpeedMenu.get()))

   # effective chants volume — combined master + chants offset when normalize is
   # enabled, or the direct chants volume value when normalize is disabled
   def _effectiveChantsVolume (self):
      if settings.config["normalize_volume"]:
         return combineVolume(self.masterVolumeValue, self.chantsVolumeValue)
      return self.chantsVolumeValue

   # master volume control — adjusts volume on all loaded songs and chants
   def adjustMasterVolume (self, value):
      value = int(value)
      self.masterVolumeValue = value
      # adjust all player buttons on both teams
      for team in (self.home, self.away):
         if team is not None:
            for button in team.buttons:
               button.clists.adjustVolume(value)
      # adjust all chants using the combined master + chants offset
      self.chantsManager.adjustManagerVolume(self._effectiveChantsVolume())
      # update slider color and dB label
      if self.masterVolume is not None:
         color = volumeColor(value)
         self.masterVolume.configure(bg=color, activebackground=color)
         vol = sliderToDb(value)
         if vol == "Mute":
            text = vol
         else:
            text = f"{vol} dB"
         self.masterVolumeLabel.configure(text=text)

   # chants volume control — called by either the main window or chants window
   # slider. When normalize is enabled, the slider value is a dB offset applied
   # on top of the master volume; when disabled, it is the direct chant volume.
   # Syncs both sliders so they always show the same value.
   def setChantsVolume (self, value):
      if self._syncingChantsVolume:
         return
      self._syncingChantsVolume = True
      try:
         value = int(value)
         self.chantsVolumeValue = value
         self.chantsManager.adjustManagerVolume(self._effectiveChantsVolume())
         # update main window slider UI
         if self.chantsVolume is not None:
            color = volumeColor(value)
            self.chantsVolume.configure(bg=color, activebackground=color)
            vol = sliderToDb(value)
            text = vol if vol == "Mute" else f"{vol} dB"
            self.chantsVolumeLabel.configure(text=text)
            self.chantsVolume.set(value)
         # update chants window slider UI (if window is open)
         if self.chantswindow is not None:
            cf = self.chantswindow.chantsFrame
            if cf.chantVolume is not None:
               color = volumeColor(value)
               cf.chantVolume.configure(bg=color, activebackground=color)
               if cf.chantVolumeLabel is not None:
                  vol = sliderToDb(value)
                  text = vol if vol == "Mute" else f"{vol} dB"
                  cf.chantVolumeLabel.configure(text=text)
               cf.chantVolume.set(value)
      finally:
         self._syncingChantsVolume = False

   def replaceChantButton (self, chantsList, home):
      if home:
         self.randomHome.playButton.destroy()
         self.randomHome = cWin.ChantsButton(self.middleStuff, self.chantsManager, chantsList, "Random", True, True)
         self.randomHome.playButton.grid(row=self._randomButtonRow, column=0)
      else:
         self.randomAway.playButton.destroy()
         self.randomAway = cWin.ChantsButton(self.middleStuff, self.chantsManager, chantsList, "Random", False, True)
         self.randomAway.playButton.grid(row=self._randomButtonRow, column=1)

   # open and close the chants window
   def chant_window (self):
      # this prevents multiple clicks opening multiple windows
      if self.chantswindow is not None:
         print("Manual chant window already open, attempting to take focus.")
         self.chantswindow.focus_force()
         return
      self.chantswindow = cWin.chantswindow(self, self.chantsManager)
      self.chantsManager.window = self.chantswindow

   def close (self):
      if self.chantswindow is not None:
         # destroys the chants window and resets the value to None
         self.chantswindow.destroy()
         self.chantswindow = None
         self.chantsManager.window = None

   def mainClose (self, master):
      self.stopNuclear()
      # kill any possible ongoing other threads first before closing
      self.chantsManager.endThread()
      legacy.titleCheck = False
      master.destroy()

   def legacyLoad (self, f, home, normalize_override=None):
      print("Loading music instructions from {}.".format(f))
      # store the file path so the team can be reloaded later (e.g. normalize toggle)
      if normalize_override is None:
         if home:
            self.homeFile = f
         else:
            self.awayFile = f
      # create a loading progress window
      loadWin = Toplevel(self)
      loadWin.title("Reloading" if normalize_override is not None else "Loading")
      loadWin.resizable(False, False)
      loadWin.transient(self)
      loadLabel = Label(loadWin, text="Reloading team export..." if normalize_override is not None else "Loading team export...", padx=20, pady=10)
      loadLabel.pack()
      barWidth = 300
      barHeight = 20
      loadBar = Canvas(loadWin, width=barWidth, height=barHeight, bg='#c8c8c8', highlightthickness=0)
      loadBar.pack(padx=20, pady=5)
      loadStatus = Label(loadWin, text="", padx=20, pady=10)
      loadStatus.pack()
      # grab focus so user can't interact with main window
      loadWin.grab_set()
      loadWin.update()

      # shared state between threads
      state = {"result": None, "error": None, "done": False,
               "phase": 0, "completed": 0, "total": 0, "songs_loaded": 0, "songs_total": 0}

      def progress_callback(completed, total):
         if completed == -2:
            # set song count from pre-pass
            state["songs_total"] = total
         elif completed == -1:
            # a song was loaded
            state["phase"] = 2
            state["songs_loaded"] += 1

      def worker():
         try:
            result = parseLegacy(f, home=home, progress_callback=progress_callback, normalize_override=normalize_override)
            state["result"] = result
         except Exception as e:
            state["error"] = e
         state["done"] = True

      thread = threading.Thread(target=worker, daemon=True)
      thread.start()

      def poll():
         if state["done"]:
            loadWin.grab_release()
            loadWin.destroy()
            if state["error"] is not None:
               e = state["error"]
               if isinstance(e, AttributeError):
                  messagebox.showerror("AttributeError on file load.","Did you download rigdio.exe instead of rigdio.7z? Make sure that the mpv DLL is present.")
               elif isinstance(e, UnicodeDecodeError):
                  messagebox.showerror("UnicodeDecodeError on file load.","Are any of your file names using weeb/non-unicode characters? Make sure they are using only unicode characters.")
               else:
                  messagebox.showerror("Exception on file load.", e)
               raise e
            self._finishLegacyLoad(f, home, state["result"])
            return
         # update progress UI
         loadBar.delete("all")
         if state["phase"] == 2:
            if state["songs_total"] > 0:
               greenW = int(barWidth * state["songs_loaded"] / state["songs_total"])
               loadBar.create_rectangle(0, 0, greenW, barHeight, fill='#22aa22', outline='')
               loadStatus["text"] = "Loading songs... {}/{}".format(state["songs_loaded"], state["songs_total"])
            else:
               loadStatus["text"] = "Loading songs... {}".format(state["songs_loaded"])
         elif state["phase"] == 0 and state["songs_total"] > 0:
            # pre-pass done, no analysis phase (normalize off) — show empty bar ready for green
            loadStatus["text"] = "Loading songs... 0/{}".format(state["songs_total"])
         self.after(50, poll)

      self.after(50, poll)

   def _resetTeamBeforeLoad (self, home):
      """Fully reset the team currently in the given slot before it's replaced.
      Stops music, clears cached playback positions, and resets event timers —
      no confirmation dialog."""
      team = self.home if home else self.away
      if team is None:
         return
      # stop any active chant from this team
      if self.chantsManager.activeChant is not None:
         self.chantsManager.endThread()
      # full in-place reset: stop music, clear position cache, reset firstPlay/warcry
      team.reset()
      # re-enable the playback speed slider in case a song was playing
      self.disablePlaybackSpeedSlider(False)
      # reset event last-played times for this side
      self.events.reset(home)

   def _finishLegacyLoad (self, f, home, result):
      tmusic, tname, events, _sync, normalize = result
      # retrieve list of song files that could not be found
      # (song as a string instead of MediaPlayer indicates file is missing)
      missing = [
         music.song
         for player in tmusic.values()
         for music in player
         if isinstance(music.song, str)
      ]
      # raise exception and display list of missing songs in error window
      if missing:
         message = "\n\n".join(missing)
         messagebox.showerror("FileNotFoundError on file load.", message)
         raise FileNotFoundError(message)
      # this will only occur for non-rigdj .4ccm files (rigdj adds a second load of the anthems automatically if no victory anthem is provided)
      if "victory" not in tmusic:
         messagebox.showwarning("Warning","No victory anthem information in {}; victory anthem will need to be played manually.".format(f))
      if tname is None:
         messagebox.showwarning("Warning","No team name found in {}. Opponent-specific music may not function properly.".format(f))
      if home:
         self.game.home_name = tname
         if self.home is not None:
            self._resetTeamBeforeLoad(True)
            self.home.grid_forget()
            self.home.clear()
         self.home = TeamMenuLegacy(self, tname, tmusic, True, self.game, normalize=normalize)
         if self.away is not None:
            self.home.anthemButton.awayButtonHook = self.away.anthemButton
         self.home.grid(row = 1, column = 0, rowspan=2, sticky=N)
         self._updateNormalizeButton(home=True)
         # apply master volume to newly loaded team if normalize_volume is enabled
         if settings.config["normalize_volume"]:
            for button in self.home.buttons:
               button.clists.adjustVolume(self.masterVolumeValue)
         if self.chantsManager is not None:
            if "chant" in tmusic and tmusic["chant"] is not None:
               print("Got {} chants for team /{}/.".format(len(tmusic["chant"]), tname))
               for clist in tmusic["chant"]:
                  print("\t{}".format(clist.songname))
               self.chantsManager.setHome(parsed=tmusic["chant"])
            else:
               print("No chants for team /{}/.".format(tname))
               self.chantsManager.setHome(parsed=None)
            # apply volume boost to chants if the home team has louder-marked tracks
            if self.home is not None and hasattr(self.home, 'hasLouder') and self.home.hasLouder:
               self.chantsManager.applyBoost(self.home.boostValue, True)
            # re-apply the effective chants volume after setHome reset it to the
            # default (combined master + chants offset when normalize is enabled,
            # or the direct chants volume when disabled)
            self.chantsManager.adjustManagerVolume(self._effectiveChantsVolume())
         if self.events is not None:
            self.events.setHome(parsed=events)
            print("Prepared events for team /{}/.".format(tname))
      else:
         self.game.away_name = tname
         if self.away is not None:
            self._resetTeamBeforeLoad(False)
            self.away.grid_forget()
            self.away.clear()
         self.away = TeamMenuLegacy(self, tname, tmusic, False, self.game, normalize=normalize)
         if self.home is not None:
            self.home.anthemButton.awayButtonHook = self.away.anthemButton
         self.away.grid(row = 1, column = 2, rowspan=2, sticky=N)
         self._updateNormalizeButton(home=False)
         # apply master volume to newly loaded team if normalize_volume is enabled
         if settings.config["normalize_volume"]:
            for button in self.away.buttons:
               button.clists.adjustVolume(self.masterVolumeValue)
         if self.chantsManager is not None:
            if "chant" in tmusic and tmusic["chant"] is not None:
               print("Got {} chants for team /{}/.".format(len(tmusic["chant"]), tname))
               for clist in tmusic["chant"]:
                  print("\t{}".format(clist.songname))
               self.chantsManager.setAway(parsed=tmusic["chant"])
            else:
               print("No chants for team /{}/.".format(tname))
               self.chantsManager.setAway(parsed=None)
            # apply volume boost to chants if the away team has louder-marked tracks
            if self.away is not None and hasattr(self.away, 'hasLouder') and self.away.hasLouder:
               self.chantsManager.applyBoost(self.away.boostValue, False)
            # re-apply the effective chants volume after setAway reset it to the
            # default (combined master + chants offset when normalize is enabled,
            # or the direct chants volume when disabled)
            self.chantsManager.adjustManagerVolume(self._effectiveChantsVolume())
         if self.events is not None:
            self.events.setAway(parsed=events)
            print("Prepared events for team /{}/.".format(tname))
      self.scoreWidget.updateLabels()
      self.game.clear()
      self.scoreWidget.updateScore()

   def resetTeam (self, home = True):
      team = self.home if home else self.away
      if team is None:
         print("No {} team loaded to reset.".format("home" if home else "away"))
         return
      confirm = messagebox.askyesno("Reset Team",
         "Reset everything the {} team is currently using? This will stop their music, clear their chants and events, and reset their score.".format("home" if home else "away"),
         icon='question')
      if not confirm:
         return
      # stop any active chant from this team
      if self.chantsManager.activeChant is not None:
         self.chantsManager.endThread()
      # in-place reset of all music buttons (pauses songs, seeks to 0, resets warcry/firstPlay)
      team.reset()
      # re-enable the playback speed slider in case a song was playing
      self.disablePlaybackSpeedSlider(False)
      # rebuild chant random lists from existing chants (no file reloading)
      chants = self.chantsManager.homeChants if home else self.chantsManager.awayChants
      if home:
         self.chantsManager.setHome(parsed=chants)
         if hasattr(team, 'hasLouder') and team.hasLouder:
            self.chantsManager.applyBoost(team.boostValue, True)
      else:
         self.chantsManager.setAway(parsed=chants)
         if hasattr(team, 'hasLouder') and team.hasLouder:
            self.chantsManager.applyBoost(team.boostValue, False)
      # reset event last-played times
      self.events.reset(home)
      # reset the score for this team
      self.game.clearTeam(home)
      # update the score widget
      self.scoreWidget.updateScore()
      print("{} team reset.".format("Home" if home else "Away"))

   # update the per-team normalize toggle button to reflect the loaded team's state
   def _updateNormalizeButton (self, home):
      btn = self.normalizeButtons.get(home)
      if btn is None:
         return
      team = self.home if home else self.away
      if team is None:
         btn.configure(text="Normalize: Yes", state=DISABLED, font="TkDefaultFont")
         return
      btn.configure(state=NORMAL)
      if team.normalize:
         btn.configure(text="Normalize: Yes", font="TkDefaultFont")
      else:
         btn.configure(text="Normalize: No", font="TkDefaultFont 9 bold")

   # re-apply the normalization audio filter to any song from the given side
   # that is currently playing, so a normalize toggle takes effect live on the
   # currently playing track instead of only on the next play()
   def _applyNormalizeToPlaying (self, home):
      team = self.home if home else self.away
      if team is None:
         return
      playing = []
      # team goalhorns / anthem / victory anthem
      for button in team.buttons:
         cp = button.clists.song
         if cp is not None and hasattr(cp.song, 'pause'):
            if not cp.song.pause and not cp.song.eof_reached:
               playing.append(cp)
      # the active chant, if it belongs to the toggled side
      if self.chantsManager is not None:
         chant = self.chantsManager.activeChant
         if chant is not None and getattr(chant, 'home', None) == home and hasattr(chant.song, 'pause'):
            if not chant.song.pause and not chant.song.eof_reached:
               playing.append(chant)
      for cp in playing:
         cp.applyNormalizeFilter()

   # toggle normalization for a loaded team on click of the Normalize button
   def toggleNormalize (self, home):
      team = self.home if home else self.away
      if team is None:
         return
      newval = not team.normalize
      if newval:
         # No -> Yes: just flip the flag and compute loudness in the background.
         # The loaded files (possibly _normalized) can be re-analyzed at runtime,
         # so there's no need to reload the whole team.
         team.setNormalize(newval)
         chants = self.chantsManager.homeChants if home else self.chantsManager.awayChants
         for chant in chants:
            if hasattr(chant, 'normalize'):
               chant.normalize = newval
         self._updateNormalizeButton(home)
         filepaths = team.allSongPaths(chants)
         chant_paths = [c.songname for c in chants if hasattr(c, 'songname')]
         anthem_paths = [c.songname for c in team.players.get("anthem", []) if hasattr(c, 'songname')]
         victory_paths = [c.songname for c in team.players.get("victory", []) if hasattr(c, 'songname')]
         legacy.start_background_analysis(filepaths, settings.level["target"],
            chant_paths=chant_paths, anthem_paths=anthem_paths, victory_paths=victory_paths)
         # re-apply the new normalized baseline to any currently playing track;
         # run in a background thread because analyze_loudness may block while
         # the background analysis pool catches up on the currently playing file
         threading.Thread(target=self._applyNormalizeToPlaying, args=(home,), daemon=True).start()
      else:
         # Yes -> No: check if any _normalized files exist in the folder that
         # we haven't already loaded; if so, reload the team so songCheck picks
         # them up. If none exist, the loaded files are already correct and we
         # just flip the flag (they'll play at 0 dB baseline as intended).
         chants = self.chantsManager.homeChants if home else self.chantsManager.awayChants
         if self._hasNormalizedToSwap(team, chants):
            filepath = self.homeFile if home else self.awayFile
            if filepath is None:
               return
            self.legacyLoad(filepath, home, normalize_override=newval)
         else:
            team.setNormalize(newval)
            for chant in chants:
               if hasattr(chant, 'normalize'):
                  chant.normalize = newval
            self._updateNormalizeButton(home)
            # re-apply the 0 dB baseline to any currently playing track live
            self._applyNormalizeToPlaying(home)

   # check whether the folder contains _normalized versions of the team's songs
   # that are not already the files currently loaded
   def _hasNormalizedToSwap (self, team, chants):
      from os.path import dirname, splitext, abspath
      from os import listdir
      # collect all loaded song paths for the team
      loaded = set()
      folders = set()
      for path in team.allSongPaths(chants):
         full = abspath(path).lower()
         loaded.add(full)
         folders.add(dirname(full))
      # check each folder for _normalized files not already loaded
      for folder in folders:
         try:
            files = listdir(folder)
         except OSError:
            continue
         for file in files:
            stem, _ = splitext(file)
            if stem.lower().endswith("_normalized"):
               if abspath(folder + "/" + file).lower() not in loaded:
                  return True
      return False

   def loadFile (self, home = True):
      f = filedialog.askopenfilename(filetypes = (("Rigdio export files", "*.4ccm"),("All files","*.*")))
      if f == "":
         # do nothing if cancel was pressed
         return
      elif isfile(f):
         extension = splitext(f)[1]
         if extension == ".4ccm":
            self.legacyLoad(f,home)
         else:
            messagebox.showerror("Error","File type {} not supported.".format(extension))
            return
      else:
         messagebox.showerror("Error","File {} not found.".format(f))

   def openSettings (self):
      # keep a reference so the SettingsWindow (and its IntVars) aren't
      # garbage-collected while the Toplevel is still open
      self.settingsWin = settingswindow.SettingsWindow(self)

def resource_path(relative_path):
   """ Get absolute path to resource, works for dev and for PyInstaller """
   try:
      # PyInstaller creates a temp folder and stores path in _MEIPASS
      base_path = sys._MEIPASS
   except Exception:
      base_path = abspath(".")
   return join(base_path, relative_path)

def main ():
   master = Tk()
   try:
      datafile = resource_path("rigdio.ico")
      master.iconbitmap(default=datafile)
   except:
      pass

   # change window palette to dark mode if enabled in config
   if settings.config["dark_mode_enabled"]:
      applyDarkMode(master)
   else:
      applyLightMode(master)
   master.title("rigdio {}".format(version))
   rigdio = Rigdio(master)
   rigdio.pack()
   master.protocol('WM_DELETE_WINDOW', lambda: rigdio.mainClose(master))
   # if config file was generated, ask if user wants to open settings
   if settings.fileGen:
      if openConfig():
         rigdio.openSettings()
   try:
      mainloop()
   except RuntimeError as e:
      print("Error occurred: {}".format(e))
      return
   except KeyboardInterrupt:
      return

if __name__ == '__main__':
   if len(sys.argv) > 1 and sys.argv[1] == "genconfig":
      print("Generating config file rigdio.yml")
      genConfig()
   else:
      main()
