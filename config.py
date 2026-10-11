import yaml
from logger import startLog
from tkinter import *
from tkinter import messagebox


defaults = dict(
   config=dict(
      alphabetical_sort_goalhorns=0, # sort player goalhorns alphabetically
      alphabetical_sort_chants=0, # sort team chants alphabetically
      chant_timer_enabled_default=1, # enable chant timer by default
      chant_random_decay_weight=0.3, # base for exponential decay weighting when picking random chants (lower = less repeat)
      chant_loud_part_percent=20, # percentage of loudest 1-second windows used as normalization reference for chants (0-100; lower targets only the loudest part, 100 = whole-track mean)
      dark_mode_enabled=0, # enable dark mode
      show_goalhorn_volume_default=1, # show goalhorn volume sliders by default
      normalize_volume=1, # normalize all music to a consistent loudness level (uses target from level config); replaces individual volume sliders with a single master volume slider
      write_song_title_log=0, # write a title.log file that contains the current song's title/filename before clearing it, values above 0 set the timer in seconds, -1 keeps it for the whole song
      write_to_log=1, # allow rigdio/rigdj to write log files (some systems don't allow rigdio/rigdj to write to log, causing it to crash)
      webserver_enabled=1,
      webserver_port=31338
   ),
   fade=dict(
      anthem=True,
      goalhorn=True,
      chant=True,
      victory=True,
      time=2
   ),
   lightColours=dict(
      bg='#f0f0f0',
      fg='#1e1e1e',
      panel='#ffffff',
      home='#e0e0fc',
      away='#ffe0dd',
      stop='#f9fce0',
      kill='#2bb4ee',
      load='#e0fcea',
      normalize='#eae0fc',
      reset='#e0fcea'
   ),
   darkColours=dict(
      bg='#1e1e1e',
      fg='#ffffff',
      panel='#2a2a2a',
      accent='#659037',
      home='#3b3f51',
      away='#513b3b',
      stop='#4a4e2a',
      kill='#377590',
      load='#2a4e3a',
      normalize='#3a2f5f',
      reset='#2a4e3a'
   ),
   gameMinute=6.67,
   level=dict(
      target = -14.0
   ),
   match="Group"
)

def genConfig():
   # create config.yml file, return early if it already exists
   try:
      file = open("config.yml",'x')
   except:
      return False
   # fill yml file with default configs
   yaml.dump(defaults["config"], file, default_flow_style=False)
   return True

# create prompt window asking if user wishes to view config file
def openConfig():
   confirm = messagebox.askyesno("Config file created",
   "First time run detected, a config file with defaults has been created. Do you wish to open the Settings menu now?")
   return confirm

def applyDarkMode(root):
   root.tk_setPalette(
      background=settings.darkColours["bg"],
      foreground=settings.darkColours["fg"],
      activeBackground=settings.darkColours["accent"],
      activeForeground=settings.darkColours["fg"],
      highlightColor=settings.darkColours["accent"])

def applyLightMode(root):
   root.tk_setPalette(
      background=settings.lightColours["bg"],
      foreground=settings.lightColours["fg"],
      activeBackground=settings.lightColours["home"],
      activeForeground=settings.lightColours["fg"],
      highlightColor=settings.lightColours["kill"])

def saveConfig():
   """Write the current config values back to config.yml."""
   try:
      with open("config.yml", "w") as configFile:
         yaml.dump(settings.configs["config"], configFile, default_flow_style=False)
   except Exception as e:
      print("Error saving config file:", e)

def recursiveDictCheck(d, defaultD, location):
   for key in defaultD:
      if key not in d:
         print("Key {} not found in {}. Default value {} will be used.".format(key, location, defaultD[key]))
         d[key] = defaultD[key]
         continue
      elif isinstance(defaultD[key],dict):
         if not isinstance(d,dict):
            print("Key {} at {} is not a dict. Default values will be used.".format(key, location))
            d[key] = defaultD[key]
            continue
         else:
            recursiveDictCheck(d[key],defaultD[key],location+":"+str(key))

class ConfigValues:
   def __init__(self):
      # generate config file, store bool of whether file already existed
      self.fileGen = genConfig()

      if self.readWriteToLog():
         startLog("rigdio.log")
      self.loadConfig()

   def readWriteToLog(self):
      try:
         with open("config.yml") as configFile:
            configs = yaml.load(configFile, Loader=yaml.Loader)
            return configs["write_to_log"]
      except Exception as e: # error reading write_to_log, assume write_to_log is true
         print("Error reading write_to_log config:", e)
         print("Default value True will be used.")
         return True

   def loadConfig(self):
      try:
         with open("config.yml") as configFile:
            self.configs = yaml.load(configFile, Loader=yaml.Loader)
      except Exception as e: # error loading config file, use defaults
         print("Error loading config file:", e)
         print("Default values will be used.")
         self.configs = defaults
         return

      try:
         self.checkConfig()
         defaults["config"] = self.configs
         self.configs = defaults
      except Exception as e:
         print("Error checking config file:", e)
         print("This is probably a bug, rather than a config.yml problem, but it shouldn't be fatal.")
         print("Default values will be used.")
         self.configs = defaults

   def checkConfig(self):
      recursiveDictCheck(self.configs, defaults["config"], "config.yml")
      mustBeValid = [
         'alphabetical_sort_goalhorns:int',
         'alphabetical_sort_chants:int',
         'chant_timer_enabled_default:int',
         'dark_mode_enabled:int',
         'show_goalhorn_volume_default:int',
         'normalize_volume:int',
         'write_to_log:int',
         'write_song_title_log:int',
         'chant_random_decay_weight:float',
         'chant_loud_part_percent:int',
         'webserver_enabled:int',
         'webserver_port:int'
      ]
      for item in mustBeValid:
         items = item.split(':')
         entry = self.configs[items[0]]
         default = defaults["config"][items[0]]

         try:
            if items[1] == "int":
               if not isinstance(entry, int):
                  raise ValueError
            elif items[1] == "float":
               if not isinstance(entry, (int, float)):
                  raise ValueError
         except ValueError:
            print("config.yml error: {} must be {}; using default value {}.".format(items[0], items[1], default))
            self.configs[items[0]] = default

   def __getattr__(self, key):
      return self.configs[key]

if __name__ == '__main__':
   genConfig()
else:
   settings = ConfigValues()
