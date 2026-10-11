from os import listdir
from os.path import basename, splitext, isfile
from legacy import ConditionList, ConditionPlayer, start_background_analysis
from config import settings

# reserved names
reserved = set(['anthem', 'victory', 'goal', 'name', 'chant', ';event', 'sync', 'normalize'])

def parse (filename, load = True, home = True, progress_callback=None, normalize_override=None):
   """Parses a music export file and loads it into memory.
   normalize_override: if not None, forces the per-team normalize flag to this
   value, ignoring what the .4ccm file specifies. Used when the streamer toggles
   normalization after load: the team is reloaded as if the flag had been set."""
   # get location of folder
   folder = '/'.join(filename.split('/')[0:-1])+'/'
   # regular player clist collections
   players = {}
   # event
   events = {}
   filenames = {
      "goal" : "Goalhorn",
      "anthem" : "Anthem",
      "victory" : "Victory Anthem",
      "chant" : "Chant"
   }

   # open filename
   with open(filename) as f:
      lines = [line.strip() for line in f.readlines()]
      f.close()

   # get name
   while len(lines[0]) == 0 or lines[0][0] == '#':
      lines = lines[1:]
   nameline = lines[0].split(';')
   if len(nameline) < 2 or nameline[0] != "name":
      print("No team name provided at start of file; defaulting to filename")
      tname = splitext(basename(filename))[0]
   else:
      tname = nameline[1].lower()
      lines = lines[1:]

   # check for sync and normalize flags (defaults to yes for both)
   # both flags are optional and may appear in any order below the team name
   sync = True
   normalize = True
   while lines and lines[0].split(';')[0].strip().lower() in ("sync", "normalize"):
      parts = lines[0].split(';')
      flag = parts[0].strip().lower()
      val = parts[1].strip().lower() if len(parts) > 1 else ""
      enabled = val not in ("no", "off", "false", "0")
      if flag == "sync":
         sync = enabled
         print("Sync flag: {}".format("enabled" if sync else "disabled"))
      else:
         # when set to no, the manager opts out of loudness normalization;
         # the streamer can still force it back on via the per-team toggle button
         normalize = enabled
         print("Normalize flag: {}".format("enabled" if normalize else "disabled"))
      lines = lines[1:]

   # streamer-side override: force the normalize flag regardless of what the
   # .4ccm file says (used when toggling normalization after load)
   if normalize_override is not None:
      if normalize != normalize_override:
         print("Normalize flag overridden to {}.".format("enabled" if normalize_override else "disabled"))
      normalize = normalize_override

   # iterate across lines
   # pre-pass: collect song count for progress UI
   if load:
      pre_files = []
      chant_pre_files = []
      anthem_pre_files = []
      victory_pre_files = []
      for line in lines:
         if len(line) == 0 or line[0] == "#":
            continue
         data = line.split(';')
         data = [x.strip() for x in data]
         player = data[0]
         if len(data) == 1:
            default = "{} - {}.mp3" if player in reserved else "{} - {} Goalhorn.mp3"
            fancyname = filenames[player] if player in reserved else player
            default = default.format(tname, fancyname)
            data.append(default)
         filepath = songCheck(folder, data[1], normalize)
         pre_files.append(filepath)
         if player == "chant":
            chant_pre_files.append(filepath)
         elif player == "anthem":
            anthem_pre_files.append(filepath)
         elif player == "victory":
            victory_pre_files.append(filepath)
      song_count = len(pre_files)
      if progress_callback:
         progress_callback(-2, song_count)
      if settings.config["normalize_volume"] and normalize:
         start_background_analysis(pre_files, settings.level["target"],
            chant_paths=chant_pre_files, anthem_paths=anthem_pre_files, victory_paths=victory_pre_files)
   # main pass: create ConditionPlayer objects
   for line in lines:
      # ignore comments
      if len(line) == 0 or line[0] == "#":
         continue
      # split up line by ;
      data = line.split(';')
      # trim whitespace from ends of strings
      data = [x.strip() for x in data]
      player = data[0] # name of player
      if len(data) == 1:
         default = "{} - {}.mp3" if player in reserved else "{} - {} Goalhorn.mp3"
         fancyname = filenames[player] if player in reserved else player
         default = default.format(tname,fancyname)
         print("No file name specified for {}, looking for {}.".format(player, default))
         data.append(default)
      filename = folder+data[1] # location of song, relative to location of export file
      # if we're loading the songs, create ConditionPlayer objects
      if load:
         filename = songCheck(folder, data[1], normalize) # check for song file, including normalised
         songtype = player if player in ("anthem", "victory", "chant") else "goalhorn"
         clist = ConditionPlayer(
            pname=data[0],
            tname=tname,
            data=data[2:],
            songname=filename,
            home=home,
            type=songtype,
            sync=sync,
            normalize=normalize)
         if progress_callback:
            progress_callback(-1, -1)
      # otherwise, ConditionList uses less memory and doesn't make mpv calls
      else:
         clist = ConditionList(
            pname=data[0],
            tname=tname,
            data=data[2:],
            songname=filename,
            home=home)
         # when rigdj loads a .4ccm where a condition's value has spaces (special, mostgoals),
         # it will remove the accompanying square brackets, and unless the user corrects it
         # before saving, it breaks the condition's value
         # the for loop below simply adds those square brackets back in again
         # this is a very messy way to handle this very specific problem
         # but it is also the simplest
         for condition in clist.conditions:
            if condition.type() == "special":
               if condition.tokens()[0] != "" and " " in condition.tokens()[0]:
                  condition.label = "[{}]".format(condition.tokens()[0])
                  break
            else:
               if condition.type() == "mostgoals":
                  if condition.tokens()[0] != "" and " " in condition.tokens()[0]:
                     condition.specified = "[{}]".format(condition.tokens()[0])
                     break
      # add this condition list to the output list
      if clist.event is None:
         if player not in players:
            players[player] = []
         players[player].append(clist)
      # add to event list
      else:
         if clist.event not in events:
            events[clist.event] = []
         events[clist.event].append(clist)

   # copy default goalhorn onto the end of all player goalhorns
   if load:
      for name, conditions in players.items():
         if ( name not in reserved ):
            players[name].extend(players['goal'])
   print("Loaded songs for team /{}/".format(tname))
   return players, tname, events, sync, normalize

def songCheck (folder, name, normalize=True):
   normalized = splitext(name)[0] + "_normalized"
   # prefer _normalized files when normalization won't be applied to this team,
   # i.e. when global normalize_volume is off OR the team opted out via normalize;no
   if not settings.config["normalize_volume"] or not normalize:
      for file in listdir(folder):
         if splitext(file)[0].lower() == normalized.lower():
            print("Normalized version of " + folder+name + " found")
            return folder+file
   # check for regular song file
   # required due to linux's file system being case-sensitive
   if not isfile(folder+name):
      for file in listdir(folder):
         if file.lower() == name.lower():
            return folder+file
   else:
      return folder+name
   # no regular file found; fall back to _normalized version if it exists
   # (will be renormalized at playback if normalization is enabled for this team)
   for file in listdir(folder):
      if splitext(file)[0].lower() == normalized.lower():
         print("Regular file not found, using normalized version of " + folder+name)
         return folder+file
   return folder+name

def main ():
   file, _tname, _events, _sync, _normalize = parse("./music/4cc/m/m.4ccm")
   file["Char's Zaku II"][0].song.pause = False
   time.sleep(15)
   file["Char's Zaku II"][0].song.pause = True
   time.sleep(5)
   file["Char's Zaku II"][0].song.pause = False
   while True:
      pass

if __name__ == '__main__':
   import time
   main()
