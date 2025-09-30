import yaml
from logger import startLog
from tkinter import *
from tkinter import messagebox


defaults = dict(
   config=dict(
      alphabetical_sort_goalhorns=0, # sort player goalhorns alphabetically
      alphabetical_sort_chants=0, # sort team chants alphabetically
      chant_timer_enabled_default=1, # enable chant timer by default
      show_goalhorn_volume_default=0, # show goalhorn volume sliders by default
      write_to_log=1 # allow rigdio/rigdj to write log files (some systems don't allow rigdio/rigdj to write to log, causing it to crash)
   ),
   fade=dict(
      anthem=True,
      goalhorn=True,
      time=2
   ),
   colours=dict(
      home='#e0e0fc',
      away='#ffe0dd'
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
      return
   # fill yml file with default configs
   yaml.dump(defaults["config"], file, default_flow_style=False)



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
      genConfig()

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
                      'show_goalhorn_volume_default:int',
                      'write_to_log:int'
                    ]
      for item in mustBeValid:
         items = item.split(':')
         entry = self.configs[items[0]]
         default = defaults["config"][items[0]]

         try:
            if items[1] == "int":
               if not isinstance(entry, int):
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
