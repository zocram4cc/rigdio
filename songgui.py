from tkinter import *
import os.path
import tkinter.messagebox as messagebox
from rigparse import reserved
from rigdio_except import UnloadSong, SongNotFound
from legacy import PlayerManager
from config import settings
from rigdio_util import volumeColor
from time import sleep

class PlayerButtons:
   def __init__ (self, frame, clists, home, game, text = None):
      # song information
      self.clists = PlayerManager(clists,home,game,self)
      self.game = game
      # derived information
      self.song = None
      self.pname = clists[0].pname
      # text and buttons
      self.text = text
      self.frame = frame
      # used for anthem handling
      # determine if this is an anthem/VA button
      self.anthem = (self.pname == "anthem")
      self.victoryAnthem = (self.pname == "victory")
      # timer stuff
      if self.victoryAnthem:
         # mpv takes some time to retrieve song duration, so a sleep delay is needed
         self.timer = Timer(self, self.frame, 1)
      # check if text is none (most players)
      if self.text is None:
         self.text = "\n".join([x.lstrip() for x in self.pname.split(",")])
         self.reserved = False
      else:
         self.reserved = True
      ## Home anthem button is hooked to this by the main client, to stop it when it starts
      self.awayButtonHook = None
      self.showVolume = True
      # text was specified, so this is a button for a reserved keyword
      self.colours = settings.darkColours if settings.config["dark_mode_enabled"] else settings.lightColours
      self.normalize = settings.config["normalize_volume"]
      if self.normalize:
         self.volumeButton = None
         self.volume = None
      else:
         self.volumeButton = Button(self.frame, text="🔊", command=self.showHideVolume, bg=self.colours["home" if home else "away"])
         self.volume = Scale(self.frame, from_=0, to=200, orient=HORIZONTAL, command=self._volumeCommand, showvalue=0, troughcolor='#c8c8c8', bd=0, highlightthickness=0)
         self.volume.set(100)
         self.volume.configure(bg=volumeColor(100), activebackground=volumeColor(100))
      self.playButton = Button(self.frame, text=self.text, command=self.playSong, bg=self.colours["home" if home else "away"])
      self.resetButton = Button(self.frame, text="⟲", command=self.resetSong, bg=self.colours["home" if home else "away"])

      self.dropdownButton = None
      if self.victoryAnthem:
         self.specialVAs = self.getSpecialList(clists, home)

   def showHideVolume (self):
      if self.showVolume:
         self.volume.grid_remove()
         self.showVolume = False
      else:
         self.volume.grid()
         self.showVolume = True

   def _volumeCommand (self, value):
      self.clists.adjustVolume(value)
      color = volumeColor(int(value))
      self.volume.configure(bg=color, activebackground=color)

   def resetSong (self):
      self.clists.resetLastPlayed()
      self.playButton.configure(relief=RAISED)
      # reset the VA timer
      if self.victoryAnthem:
         self.timer.resetTimer()

   def reset (self):
      self.clists.reset()
      self.playButton.configure(relief=RAISED)
      if self.victoryAnthem:
         self.timer.resetTimer()

   def playSong (self):
      # if home team anthem, pause away team anthem
      if self.anthem and self.awayButtonHook != None:
         self.awayButtonHook.clists.pauseSong()
         self.awayButtonHook.playButton.configure(relief=RAISED)
         # wait until away anthem fades out completely to play home anthem
         if self.clists.song is None and self.awayButtonHook.clists.lastSong is not None:
            if self.awayButtonHook.clists.lastSong.fade is not None:
               sleep(2)
      if self.clists.song is None:
         # score points if it's a goalhorn
         if self.pname not in reserved or self.pname == "goal":
            self.game.score(self.pname, self.clists.home)
            # snapshot pre-play state so Undo can restore it
            self.game.lastSnapshot = self.clists.snapshot()
            self.game.lastPlayerManager = self.clists
         # pass it up to the list manager
         try:
            # if this is the first time this song is being played and it has a custom playback speed set, set the slider to that speed
            # the playback speed will still use the exact value specified in the .4cc, it's just to show that it's been modified
            # after the first time, if the playback speed slider has been moved, it will use the value of the slider instead
            self.clists.playSong(self.song)
            if not self.clists.song.customSpeed:
               self.clists.song.song.speed = self.frame.master.playbackSpeedMenu.get()
            self.frame.master.disablePlaybackSpeedSlider(True)
         # no song found
         except SongNotFound as e:
            print(e)
            messagebox.showwarning(e)
            return
         # set the button as sunken
         self.playButton.configure(relief=SUNKEN)
      else:
         # enable the playback slider and pause the song
         self.frame.master.disablePlaybackSpeedSlider(False)
         self.clists.pauseSong()
         # pause the VA timer
         if self.victoryAnthem:
            self.timer.timerPause()
         # set the button as raised
         self.playButton.configure(relief=RAISED)

   # now deprecated, but useful for bug testing
   def showSongs (self):
      text = self.text
      if not self.reserved:
         text = "Player {}".format(self.text)
      title = "Listing Songs for {}".format(text)
      text = ""
      for clist in self.clists:
         if len(text) == 0:
            text = str(clist)
         else:
            text = "\n".join([text, str(clist)])
      messagebox.showinfo(title, text)

   def insert (self, row):
      if self.volumeButton is not None:
         self.volumeButton.grid(row=row,column=0,sticky=N+S,padx=2,pady=(5,0))
      if self.dropdownButton is not None:
         self.playButton.grid(row=row,column=1,sticky=NE+SW,padx=(2,0),pady=(5,0))
         self.dropdownButton.grid(row=row,column=2,sticky=NS+W,pady=(5,0))
      else:
         self.playButton.grid(row=row,column=1,columnspan=2,sticky=NE+SW,padx=2,pady=(5,0))
      self.resetButton.grid(row=row,column=3,sticky=N+S,padx=2,pady=(5,0))
      if self.volume is not None:
         self.volume.grid(row=row+1,column=0,columnspan=4,sticky=E+W,pady=(0,5))

   # change what song the VA button will play (default/special)
   def changeVA (self, *args):
      if self.selected.get() == "Default":
         self.playButton.config(text="Victory Anthem", command=self.playSong)
         self.song = None
      else:
         self.playButton.config(text=self.selected.get())
         self.song = self.getSpecial()

   # retrieve and return a list of all special VAs
   def getSpecialList (self, clists, home):
      specialVAs = []
      specialVALabels = []
      for clist in clists:
         for condition in clist.conditions:
            if condition.type() == 'special':
               specialVAs.append(clist)
               # if the special VA has a custom label then use it
               # otherwise just use its filename
               if condition.tokens()[0] != "":
                  specialVALabels.append(condition.tokens()[0])
               else:
                  specialVALabels.append(os.path.basename(clist.songname))
               break
      if not specialVAs:
         return specialVAs
      self.dropdownButton = Menubutton(self.frame, text="▼", relief=RAISED, bg=self.colours["home" if home else "away"])
      menu = Menu(self.dropdownButton, tearoff=False)
      self.dropdownButton.configure(menu=menu)
      self.selected = StringVar()
      menu.add_radiobutton(label="Default", variable=self.selected, value="Default")
      for i in range(0, len(specialVAs)):
         menu.add_radiobutton(label=specialVALabels[i], variable=self.selected, value=specialVALabels[i])
      self.selected.trace('w', self.changeVA)
      return specialVAs

   # return the specified song from the list of special VAs
   def getSpecial (self):
      for anthem in self.specialVAs:
         for condition in anthem.conditions:
            if condition.type() == 'special':
               if condition.tokens()[0] != "":
                  if self.playButton['text'] == condition.tokens()[0]:
                     return anthem
               else:
                  if self.playButton['text'] == os.path.basename(anthem.songname):
                     return anthem
               break

class Timer:
   def __init__ (self, songui, frame, delay):
      self.frame = frame
      self.songui = songui
      self.delay = delay
      self.timer = int()
      self.songDuration = int()
      self.stopCounting = False

   # have a sleep delay to retrieve song duration before starting up the timer
   def retrieveSongInfo (self):
      sleep(self.delay)
      self.songDuration = int(self.songui.clists.song.song.duration)
      self.timerStart()

   def timerStart (self):
      # increases the timer by the sleep delay (that occurs when starting the VA) before starting the counting loop
      self.timer += self.delay
      self.frame.updateSongTimer(self.timer, self.songDuration)
      self.frame.after(1000, self.timerCountSecond)

   # used to stop the timer loop
   def timerPause (self):
      self.stopCounting = True

   # updates the song timer by one second in a loop
   def timerCountSecond (self):
      # if the song is paused, don't loop instead and reset the bool
      if self.stopCounting:
         self.stopCounting = False
      else:
         self.timer += 1
         self.frame.updateSongTimer(self.timer, self.songDuration)
         self.frame.after(1000, self.timerCountSecond)

   # resets the internal and UI timers to 0
   def resetTimer (self):
      self.timer = 0
      self.frame.updateSongTimer(0, 0)

class TeamMenuLegacy (Frame):
   def __init__ (self, master, tname, players, home, game, normalize=True):
      Frame.__init__(self, master)
      # store information from constructor
      self.master = master
      self.tname = tname
      self.players = players
      self.home = home
      self.game = game
      # per-team normalization opt-out (only meaningful when global normalize_volume is on)
      self.normalize = normalize
      # list of player buttons
      self.buttons = []
      # list of player names for use in buttons
      self.playerNames = [x for x in self.players.keys() if x not in reserved]
      # sort the player goalhorns alphabetically depending on user's configs
      if settings.config["alphabetical_sort_goalhorns"]:
         self.playerNames.sort()
      # check if any tracks are marked louder and normalization is enabled
      self.hasLouder = False
      self.boostValue = 5
      self.blinkId = None
      self.blinkBold = False
      if settings.config["normalize_volume"]:
         for playerList in self.players.values():
            for clist in playerList:
               if hasattr(clist, 'louder') and clist.louder:
                  self.hasLouder = True
                  break
            if self.hasLouder:
               break
      # row offset: if boost slider is shown, everything shifts down by 3
      # (label row, dB value row, slider row)
      rowOffset = 3 if self.hasLouder else 0
      # volume boost slider (if applicable)
      if self.hasLouder:
         self.buildBoostSlider()
      # tkinter frame containing menu
      # victory song timer at the end
      self.buildSongTimer(rowOffset)
      # button for anthem
      self.buildAnthemButton(rowOffset)
      # buttons for victory anthems
      startRow = self.buildVictoryAnthemMenu(rowOffset) + 2
      # buttons for goalhorns
      self.buildGoalhornMenu(startRow)
      # show/hide the volume sliders for goalhorns depending on user's configs
      # (skipped when normalize_volume is enabled — no individual sliders exist)
      if not settings.config["normalize_volume"] and not settings.config["show_goalhorn_volume_default"]:
         for button in self.buttons:
            button.volume.grid_remove()
            button.showVolume = False
      # apply initial boost value to all louder-marked ConditionPlayers
      if self.hasLouder:
         self.applyBoost(self.boostValue)

   def buildBoostSlider (self):
      self.boostLabel = Label(self, text="Volume Boost")
      self.boostLabel.grid(row=0, columnspan=4, padx=2)
      self.boostDbLabel = Label(self, text="{:+d} dB".format(self.boostValue))
      self.boostDbLabel.grid(row=1, columnspan=4, padx=2)
      self.boostScale = Scale(self, from_=-5, to=15, orient=HORIZONTAL, command=self._boostCommand, showvalue=0, troughcolor='#c8c8c8', bd=0, highlightthickness=0)
      self.boostScale.set(self.boostValue)
      self.boostScale.grid(row=2, columnspan=4, sticky=E+W, padx=2)

   def _boostCommand (self, value):
      self.boostValue = int(value)
      self.boostDbLabel.configure(text="{:+d} dB".format(self.boostValue))
      self.applyBoost(self.boostValue)
      # also apply boost to chants via chantsManager
      if hasattr(self.master, 'chantsManager') and self.master.chantsManager is not None:
         self.master.chantsManager.applyBoost(self.boostValue, self.home)
      # if a boosted song is currently playing, update its af filter live
      for button in self.buttons:
         if button.clists.song is not None and button.clists.song.louder:
            if button.clists.song.normalize_gain is not None:
               total_gain = button.clists.song.normalize_gain + self.boostValue
               button.clists.song.song.af = "volume={:.1f}dB,alimiter=limit=0.95".format(total_gain)
      # also update a currently playing louder-marked chant
      if hasattr(self.master, 'chantsManager') and self.master.chantsManager is not None:
         chant = self.master.chantsManager.activeChant
         if chant is not None and hasattr(chant, 'louder') and chant.louder and chant.normalize_gain is not None:
            total_gain = chant.normalize_gain + self.boostValue
            chant.song.af = "volume={:.1f}dB,alimiter=limit=0.95".format(total_gain)

   def applyBoost (self, boostDb):
      for playerList in self.players.values():
         for clist in playerList:
            if hasattr(clist, 'louder') and clist.louder:
               clist.boostValue = boostDb

   def startBlinking (self):
      if self.blinkId is not None:
         return
      self.blinkBold = False
      self._blink()

   def stopBlinking (self):
      if self.blinkId is not None:
         self.after_cancel(self.blinkId)
         self.blinkId = None
      self.blinkBold = False
      self.boostLabel.configure(font="TkDefaultFont")

   def _blink (self):
      self.blinkBold = not self.blinkBold
      if self.blinkBold:
         self.boostLabel.configure(font="TkDefaultFont 9 bold")
      else:
         self.boostLabel.configure(font="TkDefaultFont")
      self.blinkId = self.after(1000, self._blink)

   def buildAnthemButton (self, rowOffset=0):
      self.anthemButton = PlayerButtons(self, self.players["anthem"], self.home, self.game, "Anthem")
      self.buttons.append(self.anthemButton)
      self.anthemButton.insert(2 + rowOffset)

   def buildVictoryAnthemMenu (self, rowOffset=0):
      if "victory" in self.players:
         self.victoryButton = PlayerButtons(self, self.players["victory"], self.home, self.game, "Victory Anthem")
         self.buttons.append(self.victoryButton)
         self.victoryButton.insert(4 + rowOffset)
         return 4 + rowOffset
      else:
         return rowOffset

   def buildGoalhornMenu (self, startRow):
      Label(self, text="Goalhorns").grid(row=startRow,columnspan=4)
      self.goalButton = PlayerButtons(self, self.players["goal"], self.home, self.game, "Standard Goalhorn")
      self.buttons.append(self.goalButton)
      self.goalButton.insert(startRow+1)
      for i in range(len(self.playerNames)):
         name = self.playerNames[i]
         self.playerButton = PlayerButtons(self, self.players[name], self.home, self.game)
         self.buttons.append(self.playerButton)
         self.playerButton.insert(startRow+3+2*i)

   def buildSongTimer (self, rowOffset=0):
      self.timeText = Label(self)
      self.updateSongTimer(0, 0)
      self.timeText.grid(row=rowOffset, columnspan=4)

   # updates the UI timer
   def updateSongTimer (self, timer, duration):
      timerMins = int(timer/60)
      timerSecs = timer%60
      durationMins = int(duration/60)
      durationSecs = duration%60
      self.timeText.config(text = "VA Duration - {}:{} / {}:{}".format(timerMins, str(timerSecs).zfill(2), durationMins, str(durationSecs).zfill(2)))

   def clear (self):
      for player in self.players.keys():
         for clist in self.players[player]:
            clist.disable()

   def reset (self):
      for button in self.buttons:
         button.reset()

   # set the per-team normalize flag and propagate it to every loaded ConditionPlayer
   def setNormalize (self, value):
      self.normalize = value
      for playerList in self.players.values():
         for clist in playerList:
            if hasattr(clist, 'normalize'):
               clist.normalize = value

   # return the file paths of every song loaded for this team (for background analysis)
   # chants is an optional list of chant ConditionPlayers to include
   def allSongPaths (self, chants=None):
      paths = []
      for playerList in self.players.values():
         for clist in playerList:
            if hasattr(clist, 'songname'):
               paths.append(clist.songname)
      if chants:
         paths.extend(c.songname for c in chants if hasattr(c, 'songname'))
      return paths

   def goNuclear(self):
      for playerButton in self.buttons:
         playerButton.playSong()

   def stopNuclear(self):
      for playerButton in self.buttons:
         playerButton.playSong()
         playerButton.clists.resetLastPlayed()