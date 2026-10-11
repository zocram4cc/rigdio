from version import rigdj_version as version

from io import StringIO

import sys
from os.path import abspath, join

from tkinter import *
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

from config import settings, openConfig, applyDarkMode, applyLightMode, saveConfig
from condition import *
from conditioneditor import ConditionDialog
import settingswindow

from rigdj_util import *
from uiutil import ToolTip, palette
from rigparse import parse, reserved

from logger import startLog
if __name__ == '__main__':
   # allow/forbid rigdj to write to log depending on user's configs
   if settings.config["write_to_log"]:
      startLog("rigdj.log")
   print("rigDJ {}".format(version))

specialNames = set(["Goalhorn", "Anthem", "Victory Anthem", "chant"])

class ConditionButton (Button):
   """
      Button object that opens the ConditionDialog editor.

      To be placed inside a SongRow.
   """
   def __init__ (self, songrow, index, **kwargs):
      """
         Constructs a ConditionButton.
      """
      # command and text are covered by the subclass, don't kwarg them
      if "command" in kwargs or "text" in kwargs:
         raise ValueError("Cannot specify command or text for ConditionButton.")

      # store condition, location in songrow, and the row object itself
      self.cond = songrow[index] if index < len(songrow) else None
      self.index = index
      self.songrow = songrow

      # every condition but the end one is the text on the button; if no condition, it's the new condition button
      txt = str(self.cond) if self.cond is not None else "Add Condition"
      # songrow.master is the SongEditor frame
      super().__init__(self.songrow.master, command=self.edit, text=txt, **kwargs)

   def edit (self):
      # get a condition from a ConditionDialog
      temp = ConditionDialog(self.master,self.cond,self.cond==None).condition
      # if None, was a NewCondition and Cancel was pressed
      if temp is not None:
         # if -1, existing condition asked for the delete
         if temp == -1:
            self.songrow.pop(self.index)
         # otherwise insert at the appropriate index
         else:
            if self.index < len(self.songrow):
               self.songrow[self.index] = temp
            else:
               self.songrow.append(temp)
            # store temp as this button's new condition, in case update fails for some reason
            self.cond = temp
         # check and modify status of randomise checkbox once conditions are changed
         if isinstance(self.master.master.songEditor, SongEditor):
            self.master.master.songEditor.setRandomise()
         else:
            self.master.setRandomise()
         # we've added or changed a condition, so update row and trigger callbacks
         self.songrow.update(True)

class UnrandomButton (Checkbutton):
   """
      Checkbutton widget for chants that includes/excludes them from random playbacks.

      To be placed inside a SongRow, specifically chants only.
   """
   def __init__(self, master, songrow, **kwargs):
      self.master = master
      self.songrow = songrow
      self.randomChantVar = IntVar()
      if (any(type(cond) is UnrandomInstruction for cond in songrow)):
         self.randomChantVar.set(1)
      self.button = super().__init__(self.master, text="Exclude from Random", variable=self.randomChantVar, command=self.edit, **kwargs)

   def edit(self):
      if self.randomChantVar.get() == 1:
         self.songrow.append(UnrandomInstruction(None))
      else:
         index = 0
         while index < len(self.songrow.clist):
            if type(self.songrow[index]) is UnrandomInstruction:
               self.songrow.pop(index)
            else:
               index += 1
      self.songrow.update(True)

class SongRow:
   def __init__ (self, master, songed, row, clist):
      # self.master for frame it's attached to; different from songed when multiple song rows are used
      self.master = master
      # self.songed is the SongEditor object; referenced for callbacks and drawing
      self.songed = songed
      # condition list for this row
      self.clist = clist
      # row in which to draw this row; equal to its index in self.master's clists plus 1
      self.row = row
      # row number as a string variable, for swapping of rows
      self.strRow = StringVar()
      # baseElements is all non-ConditionButton objects, constant across all SongRow objects
      self.baseElements = self.buildBaseElements()
      # conditionButtons is the
      self.conditionButtons = []
      # self.elements is a list of all elements in the row; it's baseElements + conditionButtons.
      self.elements = self.baseElements
      # initialise filename with songname and move to the end
      self.songNameEntry.insert(0,clist.songname)
      self.songNameEntry.xview_moveto(1)

   def buildBaseElements (self):
      """
         Constructs and returns the base elements of a SongRow and returns them.
      """
      output = []
      output.append(Button(self.master,text="✖", command=self.delete))
      # extra spacing because all objects get the same grid() args
      output.append(Label(self.master,text=" "))
      # down button
      output.append(Button(self.master,text="▼", command=lambda: self.songed.moveSongDown(self.row-1)))
      # shows priority
      output.append(Label(self.master,textvariable=self.strRow))
      # up button
      output.append(Button(self.master,text="▲", command=lambda: self.songed.moveSongUp(self.row-1)))
      # extra spacing because all objects get the same grid() args
      output.append(Label(self.master,text=" "))
      # open file for the song name
      output.append(Button(self.master,text="Open", command=self.openFile))
      # call updateName every time the entry is changed
      self.sv = StringVar()
      self.sv.trace_add("write", self.updateName)
      # the entry object itself
      self.songNameEntry = Entry(self.master, width=50, textvariable=self.sv, bg=palette()["panel"])
      output.append(self.songNameEntry)
      # extra spacing, if you haven't figured out the pattern yet
      output.append(Label(self.master,text=" "))
      return output

   def clear (self):
      """
         Clears all elements of this row from the master grid.
      """
      for element in self.elements:
         element.grid_forget()

   def delete (self):
      """
         Deletes this row from master.
      """
      self.clear()
      self.songed.pop(self.row-1)

   def updateName (self, *args):
      """
         Sets the song name in the clist to the song name in songNameEntry. Called automatically whenever songNameEntry changes.

         Invokes callbacks for changes.
      """
      self.clist.songname = self.songNameEntry.get()
      self.songed.callbacks()

   def update (self, callback=True):
      """
         Updates and draws this objects.

         Invokes callbacks for changes unless callback is specified as False.
      """
      self.strRow.set(str(self.row))
      for element in self.elements:
         element['state'] = 'normal'
         element.grid_forget()

      # disable arrows if the row is inappropriate
      if self.row == 1:
         self.baseElements[4]['state'] = 'disabled'
      if self.row == self.songed.count():
         self.baseElements[2]['state'] = 'disabled'

      if self.master.master.current == 'chant':
         # for chants, build only a check button to include/exclude from random playback
         self.conditionButtons = [UnrandomButton(self.master, self)]
      else:
         # construct condition buttons
         self.conditionButtons = [ConditionButton(self,index) for index in range(len(self.clist))]
         # if new conditions are not allowed, disable the 'Add Condition' button
         if self.checkNewConditions():
            self.conditionButtons.append(ConditionButton(self,len(self)))
      # construct complete list of elements
      self.elements = self.baseElements + self.conditionButtons
      # draw elements
      for index in range(len(self.elements)):
         self.elements[index].grid(row=self.row,column=index,sticky=N+E+W+S,padx=2,pady=1)
      if callback:
         self.songed.callbacks()
         self.songed.after_idle(self.songed.updateFrameSize)

   def checkNewConditions (self):
      # if the song has the randomise instruction or special condition, prevent new conditions from being added
      for instruction in self.clist.instructions:
         if instruction.type() == 'randomise':
            return False
      for condition in self.clist.conditions:
         if condition.type() == 'special':
            return False
      return True

   def openFile (self):
      # get a file
      filename = filedialog.askopenfilename(filetypes = (("Music files", "*.mp3 *.ogg *.opus *.flac *.m4a *.wav"),("All files","*")))
      # insert into songNameEntry (callback automatically invoked)
      self.songNameEntry.delete(0,END)
      self.songNameEntry.insert(0,filename)
      self.songNameEntry.xview_moveto(1)

   def pop (self, index=0):
      """
         Removes a Condition or Instruction object from the contained ConditionList.
      """
      temp = self.clist.pop(index)
      # call update, drawing and invoking calbacks
      self.update()
      return temp

   def append (self, element):
      """
         Adds a Condition or Instruction object to the end of the contained ConditionList.
      """
      self.clist.append(element)
      # call update, drawing and invoking callbacks
      self.update()

   def __getitem__ (self, index):
      """
         Provides clist access without directly using self.clist.
      """
      return self.clist[index]

   def __setitem__ (self, index, value):
      """
         Provides clist access without directly using self.clist.
      """
      self.clist[index] = value

   def __len__ (self):
      """
         Provides clist access without directly using self.clist.
      """
      return len(self.clist)

class SongEditor (Frame):
   def __init__ (self, master, canvas, clists = []):
      """
         Constructor.
      """
      # frame init — match the main background, not the panel
      super().__init__(canvas, bg=palette()["bg"])
      # songrows is empty to start
      self.songrows = []
      self.newSongButton = Button(self,text="Add Song",command=self.addSong)
      self.registered = []
      # master reference to access checkbox
      self.master = master
      # canvas reference to canvas that contains this frame
      self.canvas = canvas
      # used to check if button has been randomised
      self.buttonRandomised = False
      # prepare widgets needed for the special VA section
      self.loadSpecialVA()
      # load clists into songrows as needed
      self.load(clists)
      # necessary callbacks: update previewer and update own information, whenever stuff changes
      self.register(master.updateCurrent)
      self.register(master.editor.updateEditor)
      # bind scrollwheel to work only when mouse is in editor frame
      self.bind('<Enter>', self.bound)
      self.bind('<Leave>', self.unbound)

   def load (self, clists):
      """
         Load the given condition lists into the song editor.
      """
      # clear previous information
      for child in self.winfo_children():
         child.grid_forget()
      # if the special VA frame is visible, hide it first
      if self.specialVisible:
         for child in self.specialFrame.winfo_children():
            child.grid_forget()
         self.specialFrame.grid_forget()
         self.specialVisible = False
      # reconstruct
      self.songrows = []
      # if current player is the victory anthem, find the special victory anthems
      if self.master.current == "Victory Anthem":
         for index in range(len(clists)):
            special = False
            for instruction in clists[index]:
               if instruction.type() == 'special':
                  special = True
                  break
            if special:
               # turn special VAs into song rows and bind them to the special VA section
               self.songrows.append(SongRow(self.specialFrame,self,index+1,clists[index]))
            else:
               # bind the normal VAs to the regular SongEditor section
               self.songrows.append(SongRow(self,self,index+1,clists[index]))
      # else, just turn clists into song rows like usual
      else:
         for index in range(len(clists)):
            self.songrows.append(SongRow(self,self,index+1,clists[index]))
      # update, but don't invoke callbacks, since loading a player's entries doesn't change the .4ccm
      self.update(True, False)

   def loadSpecialVA (self):
      """
         Create the widgets needed for the special VA section.
      """
      self.specialFrame = Frame(self.master)
      self.specialVisible = False
      self.newSongButtonSpecial = Button(self.specialFrame, text="Add Song",command=self.addSongSpecial)
      self.specialLabel = Label(self.specialFrame,text="Special Victory Anthems")

   def addSong (self):
      """
         Add a new empty song row.
      """
      self.songrows.append(SongRow(self,self,len(self.songrows)+1,ConditionList()))
      # update; only need to add headings if this was the first row
      self.update(len(self.songrows)==1)

   def addSongSpecial (self):
      """
         Add a new empty song row to the special VA section.
      """
      song = SongRow(self.specialFrame,self,len(self.songrows)+1,ConditionList())
      song.append(SpecialCondition(""))
      self.songrows.append(song)
      self.update(len(self.songrows)==1)

   def callbacks (self):
      for callback in self.registered:
         callback()

   def update (self, headings = False, callback = True):
      """
         Updates every SongRow object and constructs surrounding elements as needed.
      """
      # check and modify status of randomise checkbox
      self.setRandomise()
      # update every song row
      for index in range(len(self.songrows)):
         songrow = self.songrows[index]
         songrow.row = index+1
         # don't invoke callbacks on a per-row basis, they'll be called at the end if needed
         songrow.update(callback=False)
      # check if we should add headings
      # special VA uses songrows list too, it will load even if special VAs are made first
      if len(self.songrows) > 0 and headings:
         Label(self,text="Priority").grid(row=0,column=2,columnspan=3,sticky=E+W)
         Label(self,text="Song Location").grid(row=0,column=6,columnspan=2,sticky=E+W)
         Label(self,text="Conditions").grid(row=0,column=9,columnspan=999,sticky=W)
      # move the new song button
      self.newSongButton.grid_forget()
      self.newSongButton.grid(row=len(self.songrows)+1,column=0,columnspan=3,sticky=E+W, padx=2, pady=2)
      # if current player is the victory anthem, load special VA section
      if self.master.current == "Victory Anthem":
         self.updateSpecial()
      # invoke callbacks if needed
      if callback:
         self.callbacks()
      # only update scroll region and frame width after all other tasks have finished
      self.after_idle(self.updateFrameSize)

   # set scrolling region to length of frame and adjust frame width to fit everything
   def updateFrameSize(self):
      self.canvas.configure(scrollregion=self.canvas.bbox("all"))
      self.canvas.config(width=self.winfo_width())

   # updates songeditor to include special VA section
   def updateSpecial (self):
      self.specialFrame.grid(row=len(self.songrows)+3,column=1,rowspan=3,sticky=NW,padx=5,pady=5)
      self.specialVisible = True
      # load special VA section title
      self.specialLabel.grid_forget()
      self.specialLabel.grid(row=0,column=0,columnspan=999,sticky=E+W, padx=2, pady=2)
      # use the same song row list as the regular section, they're
      for index in range(len(self.songrows)):
         songrow = self.songrows[index]
         songrow.row = index+1
         songrow.update(callback=False)

      # move the special VA new song button (using songrows guarantees it stays at the bottom of the frame)
      self.newSongButtonSpecial.grid_forget()
      self.newSongButtonSpecial.grid(row=len(self.songrows)+1,column=0,columnspan=3,sticky=E+W, padx=2, pady=2)

   def setRandomise (self):
      """
         Checks whether the currently selected player has their songs randomised or not, and sets the randomise checkbox's status accordingly
      """
      clists = self.clists()
      # if there are no horns, set the value to false
      if len(clists) == 0:
            self.buttonRandomised = False
      # checks if the selected player already has its horns randomised
      i = 0
      while i < len(clists):
         self.checkOkay = False
         # loops through the list of conditions and instructions, breaks once a randomise instruction is found
         for cond in clists[i]:
            # do not count songs with advance/special instructions on them
            if cond.type() in ['randomise', 'advance', 'special']:
               self.checkOkay = True
               break
         # if no randomise instruction is found, set the value to false and break the loop
         # otherwise, check condition list of the next horn
         if not self.checkOkay:
            self.buttonRandomised = False
            break
         else:
            self.buttonRandomised = True
            i += 1
      # if songs are randomised, check the randomise button checkbox and set the variable assigned to it to 1
      if self.buttonRandomised:
         self.master.randomHornVar.set(1)
         self.master.randomiseButton.select()
         return True
      # otherwise, uncheck it and set the variable to 0
      else:
         self.master.randomHornVar.set(0)
         self.master.randomiseButton.deselect()
         return False

   def moveSongUp (self, index):
      """
         Moves the song at the given index up one place (decreases index).
      """
      temp = self.songrows.pop(index)
      self.songrows.insert(index-1,temp)
      self.update()

   def moveSongDown (self, index):
      """
         Moves the song at the given index down one place (increases index).
      """
      temp = self.songrows.pop(index)
      self.songrows.insert(index+1,temp)
      self.update()

   def pop (self, index=0):
      """
         Deletes the song at the given index.
      """
      temp = self.songrows.pop(index)
      self.update()
      return(temp)

   def clists (self):
      """
         Gets the current condition lists.

         It might be useful to call update() before this to make sure all information is up to date.
      """
      return [row.clist for row in self.songrows]

   def count (self):
      """
         Gets the number of SongRow objects managed in the object. Can't use __len__ because tkinter needs it.
      """
      return len(self.songrows)

   def register (self, callback):
      self.registered.append(callback)

   # event handlers so that scrollwheel works for scrollbar
   def bound(self, event):
      """
         Binds mousewheel to scroll through editor frame.
      """
      self.canvas.bind_all("<MouseWheel>", self.scroll)

   def unbound(self, event):
      """
         Unbinds the mousewheel scroll.
      """
      self.canvas.unbind_all("<MouseWheel>")

   def scroll(self, event):
      """
         Scrolls frame up/down according to user's scroll input direction. (num is used for Linux while delta is used Windows/Mac)
      """
      if event.num == 5 or event.delta == -120:
         self.canvas.yview_scroll(1, "units")
      elif event.num == 4 or event.delta == 120:
         self.canvas.yview_scroll(-1, "units")

class PlayerSelectFrame (Frame):
   def __init__ (self, editor, command = None, players = []):
      super().__init__(editor)

      self.newPlayerEntry = Entry(self, width=30, bg=palette()["panel"])
      self.newPlayerEntry.grid(row=0,column=1, sticky=N+W,padx=5,pady=10)
      # songs for each player
      self.songs = {
         "Anthem" : [],
         "Victory Anthem" : [],
         "Goalhorn" : [],
         "chant" : []
      }
      # create list selector with default options
      # use white background in light mode for the editable panel areas
      self.playerMenu = ScrollingListbox(self,exportselection=False, bg=palette()["panel"])
      self.playerMenu.insert(END,"Anthem")
      self.playerMenu.insert(END,"Victory Anthem")
      self.playerMenu.insert(END,"Goalhorn")
      self.playerMenu.insert(END,"chant")
      self.playerMenu.grid(row=2,column=0,padx=5,pady=5,sticky=N)
      self.current = None
      self.editor = editor
      # delete player
      buttonFrame = Frame(self)
      Button(buttonFrame, text="Add Player", command=self.addPlayer).pack(fill=X,pady=2)
      self.renameButton = Button(buttonFrame, text="Rename Selected", command=self.renamePlayer)
      self.renameButton.pack(fill=X,pady=2)
      self.deleteButton = Button(buttonFrame, text="Delete Selected", command=self.deletePlayer)
      self.deleteButton.pack(fill=X,pady=2)
      # randomise horns checkbox
      self.randomHornVar = IntVar()
      self.randomiseButton = Checkbutton(buttonFrame, text="Randomise Horns", variable=self.randomHornVar, command=self.randomiseHorns)
      self.randomiseButton.pack(fill=X,pady=2)
      buttonFrame.grid(row=0,column=0,padx=5,pady=5)

      # create song editor
      self.canvas = Canvas(self, bg=palette()["bg"], highlightthickness=0)
      scrollbar = Scrollbar(self, orient="vertical", command=self.canvas.yview)
      self.canvas.configure(height=300, yscrollcommand=scrollbar.set)

      self.songEditor = SongEditor(self, self.canvas)

      self.canvas.create_window((0, 0), window=self.songEditor, anchor="nw")
      scrollbar.grid(row=2,column=2,rowspan=1,sticky=NS)
      self.canvas.grid(row=2,column=1,rowspan=3,sticky=NSEW,padx=5,pady=5)
      self.grid_rowconfigure(2, weight=1, uniform="equal")
      self.grid_columnconfigure(1, weight=1, uniform="equal")

      # add any players passed to constructor
      self.updateList(players)
      # bind callback to list
      self.bindSelect(self.loadSongEditor)
      self.playerMenu.selection_set(first = 0)
      self.loadSongEditor("Anthem")

   def loadSongEditor (self, pname):
      """
         Sets the SongEditor to work with the given player name, and updates rename/delete buttons as needed.
      """
      if pname in specialNames:
         self.renameButton["state"] = 'disabled'
         self.deleteButton["state"] = 'disabled'
      else:
         self.renameButton["state"] = 'normal'
         self.deleteButton["state"] = 'normal'
      self.current = None
      clists = self.songs[pname]
      self.current = pname
      self.songEditor.load(clists)
      self.songEditor.update()

   def updateCurrent (self):
      """
         Updates the current player information to the new clists.
      """
      if self.current is not None:
         self.songs[self.current] = self.songEditor.clists()

   def updateList (self, players = []):
      """
         Sets the list box contents to the reserved names plus the contents of players.
      """
      self.playerMenu.delete(4,END)
      players.sort()
      for player in players:
         self.playerMenu.insert(END,player)
      setMaxWidth(players+list(specialNames),self.playerMenu)

   def updateSongs (self, songs):
      """
         Loads the specified dict into this structure.

         Should only be needed at load time.
      """
      self.songs = {
         "Anthem" : [],
         "Victory Anthem" : [],
         "Goalhorn" : [],
         "chant" : []
      }
      for player in self:
         if player in songs:
            self.songs[player] = songs[player]
         elif player not in specialNames:
            self.songs.delete(player)
      self.current = None
      # when a new 4ccm is loaded/created, default back to the anthem(s)
      self.setSelection(self.playerMenu.get(0,END).index("Anthem"))
      self.current = "Anthem"

   def addPlayer (self):
      """
         Inserts the value of newPlayerEntry into the Listbox.
      """
      name = self.newPlayerEntry.get()
      if name == "":
         messagebox.showwarning("Error","Player name cannot be empty.")
         return
      i = 4
      while i < self.playerMenu.size() and name > self.playerMenu.get(i):
         i += 1
      if self.playerMenu.get(i) == name:
         messagebox.showwarning("Error","Player {} already exists.".format(name))
         return
      self.playerMenu.insert(i,name)
      self.songs[name] = []
      self.setSelection(i)

   def setSelection (self,index):
      """
         Sets the selection to the player at the given index.
      """
      self.playerMenu.selection_clear(first=0,last=END)
      self.playerMenu.selection_set(first=index)
      self.loadSongEditor(pname=self.get())

   def deletePlayer (self):
      """
         Deletes the selected player.
      """
      name = self.get()
      if name in specialNames:
         messagebox.showwarning("Error","Cannot delete special song type.")
         return
      self.playerMenu.delete(self.playerMenu.curselection()[0])
      self.setSelection(0)

   def renamePlayer (self):
      """
         Renames the currently selected player to the value of newPlayerEntry.
      """
      name = self.newPlayerEntry.get()
      oldname = self.get()
      if name == oldname: # we don't need to do anything so be silent
         return
      elif name in self:
         messagebox.showwarning("Error","Cannot rename to existing player {}.".format(name))
         return
      elif name == "":
         messagebox.showwarning("Error","Player name cannot be empty.")
         return
      temp = self.songEditor.clists()
      self.deletePlayer()
      self.addPlayer()
      self.songs[name] = temp
      self.current = None
      self.loadSongEditor(pname=name)

   def randomiseHorns (self):
      """
         When checked on, sets all horns of currently selected player to have the "randomise" condition (as well as remove the 'Add Condition' button),
         which has Rigdio randomly select a horn from the list instead of following priority. Horns which have the advance or special instruction do not have the randomise instruction applied to them.
         When checked off, removes the randomise instruction from all horns.
      """
      if self.randomHornVar.get() == 1:
         for row in self.songEditor.songrows:
            noAppend = False
            for cond in row.clist:
               if cond.type() in ['randomise', 'advance', 'special']:
                  noAppend = True
                  break
            if not noAppend:
               row.append(RandomiseInstruction(None))
      else:
         for row in self.songEditor.songrows:
            x = 0
            while x < len(row.clist):
               if row.clist[x].type() == 'randomise':
                  row.pop(x)
                  continue
               else:
                  x += 1

   def get (self):
      """
         Returns the currently selected value.
      """
      index = self.playerMenu.curselection()[0]
      return self.playerMenu.get(index)

   def __getitem__ (self, index):
      """
         Access to player items for iteration.
      """
      # need to do this manually otherwise tkinter starts appending empty items to the list
      if index < 0 or index >= self.playerMenu.size():
         raise IndexError
      return self.playerMenu.get(index)

   def bindSelect (self, command):
      """
         Binds the given callback to be invoked whenever the Listbox object changes its value.

         The command should take a single string argument, which will be the value selected in the box.
      """
      def eventToName (event):
         index = int(event.widget.curselection()[0])
         return event.widget.get(index)
      self.playerMenu.bind('<<ListboxSelect>>',lambda event, copy=command: copy(eventToName(event)))

class Preview4CCM (Frame):
   def __init__ (self, master, editor, **kwargs):
      super().__init__(master, editor, **kwargs)
      self.editor = editor
      self.buffer = StringIO()
      # use the main background colour to signal the preview is read-only
      self.text = Text(self, state=DISABLED, width=60, bg=palette()["bg"])
      self.text.pack(fill=Y,expand=1)

   def update (self):
      self.buffer = StringIO()
      self.editor.writefile(self.buffer,silent=True)
      self.text['state'] = NORMAL
      self.text.delete(1.0,END)
      self.text.insert(1.0,self.buffer.getvalue())
      self.text['state'] = DISABLED

class Editor (Frame):
   def __init__ (self, master):
      # tkinter master window
      super().__init__(master)
      # colour palette (updated by toggleDarkMode)
      self.colours = settings.darkColours if settings.config["dark_mode_enabled"] else settings.lightColours
      # top bar: file menu on the left, dark mode toggle on the right
      topBar = Frame(self)
      fileMenu = self.buildFileMenu(topBar)
      fileMenu.pack(side=LEFT, anchor="nw")
      self.darkModeBtn = Button(topBar,
         text="Dark Mode: On" if settings.config["dark_mode_enabled"] else "Dark Mode: Off",
         command=self.toggleDarkMode)
      self.darkModeBtn.pack(side=RIGHT, anchor="ne")
      topBar.pack(fill=X)
      self.previewer = None
      # file name of the .4ccm
      self.filename = None
      # team flags (sync and normalize both default to yes/enabled)
      self.syncVar = IntVar(value=1)
      self.normalizeVar = IntVar(value=1)
      # team name editor and previewer
      leftFrame = Frame(self, pady=5)
      temp = Frame(leftFrame)
      Label(temp, text="Team Name:").pack(side=LEFT)
      # this makes the editor update whenever team name is modified
      self.sv = StringVar()
      self.sv.trace_add("write", self.updateEditor)
      # create the actual entry object
      self.teamEntry = Entry(temp, width=20, textvariable=self.sv, bg=palette()["panel"])
      self.teamEntry.pack(side=LEFT)

      # team flags section (sync and normalize opt-outs)
      # both flags default to enabled (checked); unchecking writes ";no" to the .4ccm
      flagsFrame = Frame(leftFrame)
      flagsRow = Frame(flagsFrame)
      flagsRow.pack(anchor="w")
      # sync flag checkbox + info icon with tooltip
      self.syncVar.trace_add("write", self.updateEditor)
      self.syncCheck = Checkbutton(flagsRow, text="Share goalhorn position (sync)",
         variable=self.syncVar)
      self.syncCheck.pack(side=LEFT)
      syncInfo = Label(flagsRow, text="ⓘ", fg=palette()["fg"], cursor="question_arrow")
      syncInfo.pack(side=LEFT, padx=(2,33))
      ToolTip(syncInfo,
         "When enabled, goalhorn songs used by multiple players resume\n"
         "from where they left off when switching between players.\n"
         "Uncheck if you want every player to have their own unique copy\n"
         "of those songs, so they'll always play from the start."
      )
      # normalize flag checkbox + info icon with tooltip
      self.normalizeVar.trace_add("write", self.updateEditor)
      self.normalizeCheck = Checkbutton(flagsRow, text="Allow volume normalization",
         variable=self.normalizeVar)
      self.normalizeCheck.pack(side=LEFT)
      normInfo = Label(flagsRow, text="ⓘ", fg=palette()["fg"], cursor="question_arrow")
      normInfo.pack(side=LEFT, padx=(2,0))
      ToolTip(normInfo,
         "When enabled, rigdio analyzes each track's loudness and applies\n"
         "gain so all songs play at a consistent volume level.\n"
         "Uncheck if your export is already pre-normalized and you want\n"
         "rigdio to use the files as-is (the streamer can still force it\n"
         "back on after load, if the files are too loud or quiet)."
      )

      # player menu
      self.playerMenu = PlayerSelectFrame(self)
      # previewer
      self.previewer = Preview4CCM(leftFrame,self)
      temp.pack(anchor="w")
      flagsFrame.pack(anchor="w", pady=(5,5))
      self.previewer.pack()
      # pack playermenu after leftFrame
      leftFrame.pack(anchor="nw",side=LEFT)
      self.playerMenu.pack(anchor="nw",side=LEFT)

   def buildFileMenu (self, parent=None):
      """
         Constructs the file save/load menu buttons.
      """
      buttons = Frame(parent if parent is not None else self)
      Button(buttons, text="New .4ccm", command=self.clear4ccm).pack(side=LEFT)
      Button(buttons, text="Load .4ccm", command=self.load4ccm).pack(side=LEFT)
      Button(buttons, text="Save .4ccm", command=self.save4ccm).pack(side=LEFT)
      Button(buttons, text="Save .4ccm As...", command=self.save4ccmas).pack(side=LEFT)
      return buttons

   def toggleDarkMode (self):
      """Toggle dark mode on/off live and persist the setting to config.yml."""
      # flip the config value
      settings.configs["config"]["dark_mode_enabled"] = 0 if settings.config["dark_mode_enabled"] else 1
      self._applyDarkMode()
      # persist to config.yml
      saveConfig()
      print("Dark mode {}.".format("enabled" if settings.config["dark_mode_enabled"] else "disabled"))

   def _applyDarkMode (self):
      """Apply the current dark_mode_enabled config value to the UI."""
      dark = settings.config["dark_mode_enabled"]
      # apply the palette to the root window
      root = self.winfo_toplevel()
      if dark:
         applyDarkMode(root)
      else:
         applyLightMode(root)
      # update widget backgrounds that use explicit colours
      self.colours = palette()
      if self.previewer is not None:
         self.previewer.text.configure(bg=self.colours["bg"])
      if hasattr(self, 'playerMenu'):
         self.playerMenu.playerMenu.configure(bg=self.colours["panel"])
         self.playerMenu.canvas.configure(bg=self.colours["bg"])
         self.playerMenu.songEditor.configure(bg=self.colours["bg"])
         self.playerMenu.newPlayerEntry.configure(bg=self.colours["panel"])
         # update song name entries in existing rows
         for row in self.playerMenu.songEditor.songrows:
            if hasattr(row, 'songNameEntry'):
               row.songNameEntry.configure(bg=self.colours["panel"])
      if hasattr(self, 'teamEntry'):
         self.teamEntry.configure(bg=self.colours["panel"])
      # update the button label
      self.darkModeBtn.configure(text="Dark Mode: On" if dark else "Dark Mode: Off")

   def openSettings (self):
      # keep a reference so the SettingsWindow (and its IntVars) aren't
      # garbage-collected while the Toplevel is still open
      self.settingsWin = settingswindow.SettingsWindow(self, restart=False,
         onsave=self._onSettingsSaved)

   def _onSettingsSaved (self, changed_keys):
      # apply dark mode live if it was changed (config already has the new value)
      if "dark_mode_enabled" in changed_keys:
         self._applyDarkMode()

   def clear4ccm (self):
      self.filename = None
      self.teamEntry.delete(0,END)
      # reset team flags to defaults (both enabled)
      self.syncVar.set(1)
      self.normalizeVar.set(1)
      self.playerMenu.updateList([])
      self.playerMenu.updateSongs({})

   def updateEditor (self, *args):
      if self.previewer is not None:
         self.previewer.update()

   def load4ccm (self):
      self.filename = filedialog.askopenfilename(filetypes = (("Rigdio export files", "*.4ccm"),("All files","*")))
      songs, teamName, events, sync, normalize = parse(self.filename,False)
      uiConvert(songs)

      self.teamEntry.delete(0,END)
      self.teamEntry.insert(0,teamName)
      self.teamEntry.xview_moveto(1)
      # set team flag checkboxes from the parsed .4ccm flags
      self.syncVar.set(1 if sync else 0)
      self.normalizeVar.set(1 if normalize else 0)
      normalPlayers = [x for x in songs if x not in specialNames]
      self.playerMenu.updateList(normalPlayers)
      self.playerMenu.updateSongs(songs)
      self.updateEditor()

   def save4ccm (self):
      if self.filename is None:
         self.filename = filedialog.asksaveasfilename(defaultextension=".4ccm", filetypes = (("Rigdio export files", "*.4ccm"),("All files","*")))
      file = open(self.filename,'w')
      self.writefile(file)

   def save4ccmas (self):
      self.filename = filedialog.asksaveasfilename(defaultextension=".4ccm", filetypes = (("Rigdio export files", "*.4ccm"),("All files","*")))
      file = open(self.filename,'w')
      self.writefile(file)

   def writefile (self,outfile,silent=False):
      if self.teamEntry.get() == "" and outfile != self.previewer.buffer: # allow empty team name when writing to preview buffer
         messagebox.showerror("Error","Team name cannot be empty.")
         return None

      players = self.playerMenu.songs
      flag = False
      outConvert(players)
      print("# team identifier", file=outfile)
      print("name;{}".format(self.teamEntry.get()), file=outfile)
      # write team-level flags (only when opting out, since yes is the default)
      if self.syncVar.get() == 0:
         print("sync;no", file=outfile)
      if self.normalizeVar.get() == 0:
         print("normalize;no", file=outfile)
      print("",file=outfile)
      print("# reserved names", file=outfile)
      # count number of special VAs and see if it matches VA list length (all VAs are special)
      limit, count = len(players["victory"]), 0
      for player in players["victory"]:
         for instruction in player.instructions:
            if instruction.type() == 'special':
               count += 1
               break
      # if no regular victory anthems provided, copy normal anthem
      if outfile != self.previewer.buffer and count >= limit and (len(players["victory"]) == 0 or "victory" not in players):
         players["victory"] += players["anthem"]
      for player in self.playerMenu:
         player = outName(player)
         # if no chants provided, skip writing songs for chant player
         if player == "chant" and outfile != self.previewer.buffer and (len(players["chant"]) == 0 or "chant" not in players):
            continue
         if player not in reserved and flag == False:
            print("",file=outfile)
            print("# regular players", file=outfile)
            flag = True
         if len(players[player]) > 0:
            if not silent:
               print("Writing songs for player {}.".format(player))
            for conditions in players[player]:
               print("{};{}".format(player,conditions), file=outfile)
         else:
            if not silent:
               print("List for player {} is empty, will be ignored.").format(player)
      uiConvert(players)

def resource_path(relative_path):
   """ Get absolute path to resource, works for dev and for PyInstaller """
   try:
      # PyInstaller creates a temp folder and stores path in _MEIPASS
      base_path = sys._MEIPASS
   except Exception:
      base_path = abspath(".")
   return join(base_path, relative_path)

def main ():
   # tkinter master window
   mainWindow = Tk()
   try:
      datafile = resource_path("rigdj.ico")
      mainWindow.iconbitmap(default=datafile)
   except:
      pass
   # change window palette to dark mode if enabled in config
   if settings.config["dark_mode_enabled"]:
      applyDarkMode(mainWindow)
   else:
      applyLightMode(mainWindow)

   mainWindow.title("rigDJ {}".format(version))
   # construct editor object in window
   dj = Editor(mainWindow)
   dj.pack()
   # if config file was generated, ask if user wants to open settings
   if settings.fileGen:
      if openConfig():
         dj.openSettings()
   try:
      mainloop()
   except RuntimeError as e:
      print("Error occurred: {}".format(e))
      return

if __name__ == '__main__':
   main()
