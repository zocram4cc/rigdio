import sys
from os.path import isfile, join, abspath, splitext

from tkinter import *
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

from config import genConfig, settings

from condition import MatchCondition
from rigparse import parse as parseLegacy
from gamestate import GameState
from songgui import *
from version import rigdio_version as version
from rigdj_util import setMaxWidth
from event import EventController
import chantswindow as cWin
from webserver import start_webserver

from logger import startLog
if __name__ == '__main__':
   # allow/forbid rigdio to write to log depending on user's configs
   if settings.config["write_to_log"]:
      startLog("rigdio.log")
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
      # file menu
      Button(self, text="Load Home Team", command=self.loadFile, bg=settings.colours["home"]).grid(row=0, column=0)
      Button(self, text="Load Away Team", command=lambda: self.loadFile(False), bg=settings.colours["away"]).grid(row=0, column=2)
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
      # undo (temporary)
      Button(self, text="Undo Last Goal", command=self.game.undoLast).grid(row=3, column=1)

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
      # chaos horn
      Label(self.middleStuff, text=None).grid(columnspan=2)
      self.chaosHorn = Button(self.middleStuff, text="Chaoshorn", command=self.goNuclear, bg="#ee4b2b")
      self.chaosHorn.grid(columnspan=2)
      self.killChaos = Button(self.middleStuff, text="Kill Chaoshorn", command=self.stopNuclear, bg="#2bb4ee")
      self.killChaos.grid(columnspan=2)
      Label(self.middleStuff, text=None).grid(columnspan=2)
      # universal playback speed slider
      Label(self.middleStuff, text="Playback Speed").grid(columnspan=2)
      self.playbackSpeedMenu = Scale(self.middleStuff, from_=0.25, to=4.00, orient=HORIZONTAL, command=NONE, resolution=0.25, showvalue=1, digits=3)
      self.playbackSpeedMenu.set(1.00)
      self.playbackSpeedMenu.grid(columnspan=2)
      # creates chants window and manager
      self.chantswindow = None
      self.chantsManager = cWin.ChantsManager(self.chantswindow, self)
      # manual chant controls
      Label(self.middleStuff, text=None).grid(columnspan=2)
      Button(self.middleStuff, text="Manual Chants", command=self.chant_window).grid(columnspan=2)
      # blank space
      Label(self.middleStuff, text=None).grid(columnspan=2)
      # stop chant early button
      self.stopEarlyButton = Button(self.middleStuff, text="Stop Chant Early", command=self.chantsManager.endThread, bg="#f9fce0")
      self.stopEarlyButton.grid(columnspan=2)
      # random chant buttons accessible from the main window
      self.randomHome = cWin.ChantsButton(self.middleStuff, self.chantsManager, None, "Random", True, True)
      self.randomHome.playButton.grid(row=10, column=0)
      self.randomAway = cWin.ChantsButton(self.middleStuff, self.chantsManager, None, "Random", False, True)
      self.randomAway.playButton.grid(row=10, column=1)
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

   # used to disable the use of the playback speed slider when a song is playing, to make it obvious what the current playback speed is
   def disablePlaybackSpeedSlider (self, disable):
      if self.playbackSpeedMenu is not None:
         self.playbackSpeedMenu["state"] = DISABLED if disable else NORMAL
         self.playbackSpeedMenu["fg"] = 'grey' if disable else 'black'

   def replaceChantButton (self, chantsList, home):
      if home:
         self.randomHome.playButton.destroy()
         self.randomHome = cWin.ChantsButton(self.middleStuff, self.chantsManager, chantsList, "Random", True, True)
         self.randomHome.playButton.grid(row=10, column=0)
      else:
         self.randomAway.playButton.destroy()
         self.randomAway = cWin.ChantsButton(self.middleStuff, self.chantsManager, chantsList, "Random", False, True)
         self.randomAway.playButton.grid(row=10, column=1)

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
         # ends the ongoing chant thread early and resets setting values back to default
         self.chantsManager.endThread()
         self.chantsManager.resetValues()
         # destroys the chants window and resets the value to None
         self.chantswindow.destroy()
         self.chantswindow = None
         self.chantsManager.window = None

   def mainClose (self, master):
      self.stopNuclear()
      self.chantsManager.endThread()
      master.destroy()

   def legacyLoad (self, f, home):
      print("Loading music instructions from {}.".format(f))
      try:
         tmusic, tname, events = parseLegacy(f,home=home)
      except AttributeError as e:
         messagebox.showerror("AttributeError on file load.","Did you download rigdio.exe instead of rigdio.7z? Make sure that the libVLC DLLs and plugins directory are present.")
         raise e
      except UnicodeDecodeError as e:
         messagebox.showerror("UnicodeDecodeError on file load.","Are any of your file names using weeb/non-unicode characters? Make sure they are using only unicode characters.")
         raise e
      except Exception as e:
         messagebox.showerror("Exception on file load.", e)
         raise e
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
            self.home.grid_forget()
            self.home.clear()
         self.home = TeamMenuLegacy(self, tname, tmusic, True, self.game)
         if self.away is not None:
            self.home.anthemButton.awayButtonHook = self.away.anthemButton
         self.home.grid(row = 1, column = 0, rowspan=2, sticky=N)
         if self.chantsManager is not None:
            if "chant" in tmusic and tmusic["chant"] is not None:
               print("Got {} chants for team /{}/.".format(len(tmusic["chant"]), tname))
               for clist in tmusic["chant"]:
                  print("\t{}".format(clist.songname))
               self.chantsManager.setHome(parsed=tmusic["chant"])
            else:
               print("No chants for team /{}/.".format(tname))
               self.chantsManager.setHome(parsed=None)
         if self.events is not None:
            self.events.setHome(parsed=events)
            print("Prepared events for team /{}/.".format(tname))
      else:
         self.game.away_name = tname
         if self.away is not None:
            self.away.grid_forget()
            self.away.clear()
         self.away = TeamMenuLegacy(self, tname, tmusic, False, self.game)
         if self.home is not None:
            self.home.anthemButton.awayButtonHook = self.away.anthemButton
         self.away.grid(row = 1, column = 2, rowspan=2, sticky=N)
         if self.chantsManager is not None:
            if "chant" in tmusic and tmusic["chant"] is not None:
               print("Got {} chants for team /{}/.".format(len(tmusic["chant"]), tname))
               for clist in tmusic["chant"]:
                  print("\t{}".format(clist.songname))
               self.chantsManager.setAway(parsed=tmusic["chant"])
            else:
               print("No chants for team /{}/.".format(tname))
               self.chantsManager.setAway(parsed=None)
         if self.events is not None:
            self.events.setAway(parsed=events)
            print("Prepared events for team /{}/.".format(tname))

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
         self.scoreWidget.updateLabels()
         self.game.clear()
         self.scoreWidget.updateScore()
      else:
         messagebox.showerror("Error","File {} not found.".format(f))

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
   master.title("rigdio {}".format(version))

   rigdio = Rigdio(master)
   rigdio.pack()
   master.protocol('WM_DELETE_WINDOW', lambda: rigdio.mainClose(master))
   try:
      mainloop()
   except KeyboardInterrupt:
      return

if __name__ == '__main__':
   if len(sys.argv) > 1 and sys.argv[1] == "genconfig":
      print("Generating config file rigdio.yml")
      genConfig()
   else:
      main()