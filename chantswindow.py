from tkinter import *
from config import settings
from rigdio_util import volumeColor, sliderToDb

import os.path, threading, time, random

# chants window class
class chantswindow(Toplevel):
   def __init__(self, parent, chantsManager):
      super().__init__(parent)
      self.chantsManager = chantsManager

      # inserts the UI frame into the window
      self.chantsFrame = ChantsFrame(self, self.chantsManager)
      self.chantsFrame.pack()

      self.title("Manual Chants")
      # Change what happens when you click the X button
      # This is done so changes also reflect in the main window class
      self.protocol('WM_DELETE_WINDOW', parent.close)

# UI frame for the window
class ChantsFrame(Frame):
   def __init__(self, parent, chantsManager):
      Frame.__init__(self, parent)
      self.chantsManager = chantsManager
      # UI colour palette
      self.colours = settings.darkColours if settings.config["dark_mode_enabled"] else settings.lightColours

      # chants volume slider — always shown, mirrors the main window's chants
      # volume slider. When normalize is enabled this is a dB offset on top of
      # master volume; when disabled it is the direct chant volume control.
      Label(self, text="Chants Volume").grid(columnspan=2)
      self.chantVolumeLabel = Label(self, text="+0 dB")
      self.chantVolumeLabel.grid(columnspan=2)
      self.chantVolume = Scale(self, from_=0, to=200, orient=HORIZONTAL, command=self._volumeCommand, showvalue=0, length=150, troughcolor='#c8c8c8', bd=0, highlightthickness=0)
      # initialize to the main window's current chants volume value
      initVol = self.chantsManager.mainWin.chantsVolumeValue
      self.chantVolume.set(initVol)
      self.chantVolume.configure(bg=volumeColor(initVol), activebackground=volumeColor(initVol))
      volDb = sliderToDb(initVol)
      self.chantVolumeLabel.configure(text=volDb if volDb == "Mute" else f"{volDb} dB")
      self.chantVolume.grid(columnspan=2)
      # blank space between the sliders and chant buttons to separate them, make it look nicer
      Label(self, text=None).grid(columnspan=2)

      # chant timer checkbox, for if the user doesn't want to use it
      # set the checkbox default state depending on user's configs
      self.enableTimerCheckbox = Checkbutton(self, text="Enable Timer", variable = self.chantsManager.usingTimer, command=self.enableTimer, selectcolor=self.colours["bg"])
      self.enableTimerCheckbox.grid(columnspan=2)

      self.chantTimerText = Label(self, text="Chants Timer")
      self.chantTimerText.grid(columnspan=2)

      # chant timer slider
      self.chantTimer = Scale(self, from_=20, to=60, orient=HORIZONTAL, command=self.chantsManager.adjustTimer, resolution=5, showvalue=1, length = 150)
      self.chantTimer.set(self.chantsManager.lastTimer)
      self.chantTimer.grid(columnspan=2)
      self.enableTimer()
      # disable use of timer settings if a chant is playing when the chant window is opened
      if self.chantsManager.activeChant is not None:
         self.enableTimerCheckbox["state"] = DISABLED
         self.enableTimerCheckbox["fg"] = 'grey'

         self.chantTimerText["fg"] = 'grey'
         self.chantTimer["state"] = DISABLED
         self.chantTimer["fg"] = 'grey'
      # stop chant early button
      self.stopEarlyButton = Button(self, text="Stop Chant Early", command=self.chantsManager.endThread, bg=self.colours["stop"])
      self.stopEarlyButton.grid(columnspan=2)
      # blank space between the sliders and chant buttons to separate them, make it look nicer
      Label(self, text=None).grid(columnspan=2)

      # chants lists to replace buttons when new chants are loaded
      self.homeChantsList, self.awayChantsList = list(), list()
      self.createChants(self.chantsManager.homeChants, self.chantsManager.awayChants)

   def _volumeCommand (self, value):
      # delegate to the main window's setChantsVolume, which handles both
      # normalize on/off and syncs both sliders (including this one)
      self.chantsManager.mainWin.setChantsVolume(value)

   # creates the chant buttons
   def createChants (self, home = False, away = False):
      if self.chantsManager.activeChant:
         self.chantsManager.endThread()
      if home:
         self.clearChantList(self.homeChantsList)

         if self.chantsManager.homeChants:
            chants = self.chantsManager.homeChants
            # a chant button that plays a random chant when it's pressed
            self.randomChant = ChantsButton(self, self.chantsManager, self.chantsManager.homeRandom, "Random", True, True)
            self.randomChant.insert(8)
            self.homeChantsList.append(self.randomChant)

            for i in range(len(chants)):
               # set name on button to only show the original chant name exclusing the extension
               chantName = os.path.basename(chants[i].songname)
               chantName = os.path.splitext(chantName)[0]
               if (chantName.endswith("_normalized")):
                  chantName = chantName[:-11]
               self.chantsButton = ChantsButton(self, self.chantsManager, chants[i], chantName, chants[i].home)
               self.homeChantsList.append(self.chantsButton)
               self.chantsButton.insert(i+9)
      if away:
         self.clearChantList(self.awayChantsList)

         if self.chantsManager.awayChants:
            chants = self.chantsManager.awayChants
            # a chant button that plays a random chant when it's pressed
            self.randomChant = ChantsButton(self, self.chantsManager, self.chantsManager.awayRandom, "Random", False, True)
            self.randomChant.insert(8)
            self.awayChantsList.append(self.randomChant)

            for i in range(len(chants)):
               # set name on button to only show the original chant name exclusing the extension
               chantName = os.path.basename(chants[i].songname)
               chantName = os.path.splitext(chantName)[0]
               if (chantName.endswith("_normalized")):
                  chantName = chantName[:-11]
               self.chantsButton = ChantsButton(self, self.chantsManager, chants[i], chantName, chants[i].home)
               self.awayChantsList.append(self.chantsButton)
               self.chantsButton.insert(i+9)
      # so that any newly loaded chants follow the current slider value instead of the default
      # use setChantsVolume so the effective volume (master + chants offset when
      # normalize is enabled) is applied correctly and both sliders stay in sync
      if self.chantVolume is not None:
         self.chantsManager.mainWin.setChantsVolume(self.chantVolume.get())
      else:
         self.chantsManager.adjustManagerVolume(self.chantsManager.lastVolume)

   # clears out chants in the window
   def clearChantList (self, chantList):
      if chantList:
         for chant in chantList:
            chant.playButton.destroy()
         chantList.clear()

   # used to enable/disable the use of the timer for chants, greys out and disables the text and slider to show it better
   def enableTimer (self):
      self.chantsManager.timerEnabled = self.chantsManager.usingTimer.get()

      self.chantTimerText["fg"] = 'grey' if self.chantsManager.timerEnabled == 0 else self.colours["fg"]
      self.chantTimer["state"] = DISABLED if self.chantsManager.timerEnabled == 0 else NORMAL
      self.chantTimer["fg"] = 'grey' if self.chantsManager.timerEnabled == 0 else self.colours["fg"]
# creates and manages the chant buttons
class ChantsButton:
   def __init__ (self, frame, chantsManager, chant, text, home, random = False):
      # used to randomise the chant by having the argument take in the list of chants instead
      self.chantList = chant if random and isinstance(chant, list) else list()
      self.frame = frame
      self.chantsManager = chantsManager
      self.chant = chant
      self.text = text
      self.home = home
      self.random = random
      colours = settings.darkColours if settings.config["dark_mode_enabled"] else settings.lightColours

      # exponential decay weighting: each chant's selection weight is
      # decay_weight ^ times_played, so repeats become increasingly rare
      self.decayWeight = settings.config["chant_random_decay_weight"]
      self.playCounts = [0] * len(self.chantList)

      # how long a chant can be played for until it begins to fade out
      self.fadeOutTime = self.chantsManager.lastTimer
      self.playButton = Button(frame, text=self.text, command=self.playChant, bg=colours["home" if self.home else "away"])

   def playChant (self):
      # if there is already a chant going on, ignore command
      if self.chantsManager.activeChant is not None:
         print("Denied, chant currently playing.")
      # if team has no chants, ignore command
      elif self.random and not self.chantList:
         print("Team has no chants.")
      else:
         # pick a chant using exponential decay weighting
         if self.random:
            weights = [self.decayWeight ** count for count in self.playCounts]
            pick = random.choices(range(len(self.chantList)), weights=weights)[0]
            self.playCounts[pick] += 1
            self.chant = self.chantList[pick]
         # otherwise, set this chant as the active chant and begin playing
         self.playButton.configure(relief=SUNKEN)
         self.chantsManager.activeChant = self.chant
         self.chantEndCheck = threading.Thread(target=self.checkChantDone)
         self.chant.reloadSong()
         self.chant.play()
         print("Chant now playing.")
         print("Chant Timer: {} seconds.".format(self.fadeOutTime))
         # start blinking if the chant is louder-marked
         if hasattr(self.chant, 'louder') and self.chant.louder:
            team = self.chantsManager.mainWin.home if self.home else self.chantsManager.mainWin.away
            if team is not None and hasattr(team, 'hasLouder') and team.hasLouder:
               team.startBlinking()

         # while greying out the timer stuff and starting the chant end checker thread
         self.chantsManager.disableChantTimer(True, self.chantsManager.window.chantsFrame if self.chantsManager.window is not None else None)
         self.chantEndCheck.start()

   # checks when the chant is done or playing too long
   def checkChantDone (self):
      self.chantStart = time.time()
      while self.chantEndCheck is not None:
         # stops the thread early, before the song has finished playing
         if self.chantsManager.endThreadEarly:
            print("Chant ended early.")
            # stops the song, resets the end thread bool, and enables the chant timer (bool reset and chant timer enable is for when new chants are loaded)
            self.chant.fade = True
            self.chant.fadeOut()
            self.chantsManager.endThreadEarly = False
            if self.frame.winfo_exists():
               self.playButton.configure(relief=RAISED)
               self.chantsManager.disableChantTimer(False, self.chantsManager.window.chantsFrame if self.chantsManager.window is not None else None)
            # stop blinking if the chant was louder-marked
            self._stopChantBlink()
            # disables the fade, mark active chant as none, and kill the thread
            self.chant.fade = None
            self.chantsManager.activeChant = None
            self.chantEndCheck = None

         if self.chant.song.eof_reached:
            self.chantDone()
            self.chantEndCheck = None
         # checks if the user is even using the timer in the first place as well
         elif self.chantsManager.timerEnabled and (time.time() - self.chantStart) > self.fadeOutTime:
            print("Chant timed out, fade starting.")
            self.chant.fade = True
            self.chant.fadeOut()
            self.chantDone()
            self.chantEndCheck = None
         time.sleep(0.01)

   # clears out the active chant variable once the chant is over
   def chantDone (self):
      if self.chantsManager.activeChant is not None:
         self.chantsManager.activeChant = None
         print("Chant {} concluded.".format(self.text))
         if self.frame.winfo_exists():
            self.playButton.configure(relief=RAISED)
            self.chantsManager.disableChantTimer(False, self.chantsManager.window.chantsFrame if self.chantsManager.window is not None else None)
         self._stopChantBlink()

   def _stopChantBlink (self):
      if hasattr(self.chant, 'louder') and self.chant.louder:
         team = self.chantsManager.mainWin.home if self.home else self.chantsManager.mainWin.away
         if team is not None and hasattr(team, 'hasLouder') and team.hasLouder:
            team.stopBlinking()

   def insert (self, row):
      self.playButton.grid(row=row, column=0 if self.home else 1)

class ChantsManager:
   def __init__ (self, window, mainWin):
      self.window = window
      self.mainWin = mainWin
      # UI colour palette
      self.colours = settings.darkColours if settings.config["dark_mode_enabled"] else settings.lightColours

      # stores chant information
      self.homeChants, self.awayChants = list(), list()

      # stores chant list for random button to play
      self.homeRandom, self.awayRandom = list(), list()

      # default settings for chant timer and volume
      self.lastTimer = 30
      self.lastVolume = 100

      # chant that is currently being played
      self.activeChant = None

      # used to end the checkChantDone thread early
      self.endThreadEarly = False

      # used to check if program is using the timer
      self.usingTimer = IntVar(value=settings.config["chant_timer_enabled_default"])
      # non-tkinter-binding version of the above variable
      # required to prevent UI freeze when playing chants on chant window
      self.timerEnabled = settings.config["chant_timer_enabled_default"]

   def setHome (self, filename=None, parsed=None):
      if parsed is not None:
         self.homeChants = parsed
         self.homeRandom = self.homeChants.copy()
         # remove any chants with the 'unrandom' instruction from the random list
         index = 0
         while index < len(self.homeRandom):
            if any(item.type() == 'unrandom' for item in self.homeRandom[index].instructions):
               self.homeRandom.pop(index)
            else:
               index += 1

         # sort the team chants alphabetically depending on user's configs
         if settings.config["alphabetical_sort_chants"]:
            self.homeChants.sort(key=lambda x : x.__str__())
      else:
         print("No chants received for home team.")
         self.homeChants.clear()
         self.homeRandom.clear()

      # replaces the random chant button with the updated list of chants and set the volume back to default
      self.mainWin.replaceChantButton(self.homeRandom, True)
      self.adjustManagerVolume(self.lastVolume)

      if (self.window is not None):
         self.window.chantsFrame.createChants(home = True)

   def setAway (self, filename=None, parsed=None):
      if parsed is not None:
         self.awayChants = parsed
         self.awayRandom = self.awayChants.copy()
         # remove any chants with the 'unrandom' instruction from the random list
         index = 0
         while index < len(self.awayRandom):
            if any(item.type() == 'unrandom' for item in self.awayRandom[index].instructions):
               self.awayRandom.pop(index)
            else:
               index += 1

         # sort the team chants alphabetically depending on user's configs
         if settings.config["alphabetical_sort_chants"]:
            self.awayChants.sort(key=lambda x : x.__str__())
      else:
         print("No chants received for away team.")
         self.awayChants.clear()
         self.awayRandom.clear()

      # replaces the random chant button with the updated list of chants and set the volume back to default
      self.mainWin.replaceChantButton(self.awayRandom, False)
      self.adjustManagerVolume(self.lastVolume)

      if (self.window is not None):
         self.window.chantsFrame.createChants(away = True)

   # used to end the thread early, called by the main rigdio file when chants window is closed
   def endThread (self):
      if self.activeChant is not None:
         self.endThreadEarly = True

   # used to disable the use of the timer stuff when a chant is playing, to prevent the user from messing with it during a chant and causing problems
   def disableChantTimer(self, disable, frame=None):
      if frame is None:
         return

      frame.enableTimerCheckbox["state"] = DISABLED if disable else NORMAL
      frame.enableTimerCheckbox["fg"] = 'grey' if disable else self.colours["fg"]
      # if user is not using the timer in the first place, don't touch the text and slider
      if self.usingTimer.get():
         frame.chantTimerText["fg"] = 'grey' if disable else self.colours["fg"]
         frame.chantTimer["state"] = DISABLED if disable else NORMAL
         frame.chantTimer["fg"] = 'grey' if disable else self.colours["fg"]

   def adjustManagerVolume (self, value):
      # shoves all of the chants into a single list
      self.allChants = self.homeChants + self.awayChants

      # adjusts the volume of all the chants at the same time
      for chant in self.allChants:
         chant.adjustVolume(value)
      self.lastVolume = int(value)

   def applyBoost (self, boostDb, home):
      chants = self.homeChants if home else self.awayChants
      for chant in chants:
         if hasattr(chant, 'louder') and chant.louder:
            chant.boostValue = boostDb

   def adjustTimer (self, value):
      # shoves all of the chant buttons (including the random ones) into a single list
      self.allButtons = self.window.chantsFrame.homeChantsList + self.window.chantsFrame.awayChantsList
      self.allButtons.append(self.mainWin.randomHome)
      self.allButtons.append(self.mainWin.randomAway)

      # adjusts the fade out timer of all the chants at the same time
      for chantButton in self.allButtons:
         chantButton.fadeOutTime = float(value)
      self.lastTimer = float(value)
