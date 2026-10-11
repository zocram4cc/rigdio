import threading
from time import sleep
from os.path import basename, abspath, isfile

# needed for prompts
from tkinter import *
from tkinter.simpledialog import Dialog
import tkinter.messagebox as messagebox

from config import settings
from rigdio_except import UnloadSong, PlayNextSong
from rigdio_util import timeToSeconds

binaryOperators = set(["<", ">", "<=", ">=", "==", "!="])
unloadableOperators = set(["<", "<=", "=="])

class Condition:
   null = "nullCond"

   def __init__(self, pname = "", tname = "", home = True, **kwargs):
      super().__init__(**kwargs) # initialise Object()
      self.pname = pname
      self.tname = tname
      self.home = home

   def check(self, gamestate):
      """
         Checks if a condition is true or not.

         Arguments:
          - gamestate (GameState): state of the game.
      """
      raise NotImplementedError("Condition subclass must override check().")

   def isInstruction (self):
      """
         Checks if something is a Condition or an Instruction. There is no need to override this.

         Return:
          - <code>True</code> if the object is an Instruction, <code>False</code> if the object is a Condition.
      """
      return False

   def type (self):
      """
         Name of this condition type.

         This is the string used to mark the condition in .4ccm files.
      """
      raise NotImplementedError("Condition subclass must override type().")

   def tokens (self):
      """
         Gives this Condition as a list of tokens, EXCLUDING the type of the condition.

         In essence, these are the tokens passed to the constructor, and listed after the condition name in files.
      """
      raise NotImplementedError("Condition subclass must override tokens().")

   def __str__ (self):
      return "{} {}".format(self.type()," ".join(self.tokens())).strip()

   def __repr__ (self):
      return "buildCondition(pname={},tname={},home={},tokens={})".format(self.pname,self.tname,self.home,str(self).split(" "))

   def toYML (self):
      tokens = self.tokens()
      if len(tokens) == 0:
         tokens = None
      elif len(tokens) == 1:
         tokens = tokens[0]
      return {self.type() : tokens}

class ArithCondition (Condition):
   desc = """Superclass for all conditions that evaluate an arithmetic expression."""

   def __init__(self, **kwargs):
      super().__init__(**kwargs)

   def check (self, gamestate):
      args = self.args(gamestate)
      return eval(self.expression().format(*args))

   def args (self, gamestate):
      raise NotImplementedError("ArithCondition subclass must override args().")

   def expression (self):
      raise NotImplementedError("ArithCondition subclass must override expression().")

class GoalCondition (ArithCondition):
   desc = """Plays when the number of goals this player has scored meet the condition."""

   def __init__(self, tokens, **kwargs):
      super().__init__(**kwargs)
      if tokens[0] == "=":
         tokens[0] = "=="
      if tokens[0] not in binaryOperators:
         raise ValueError("invalid GoalCondition operator "+tokens[0]+"; valid operators are "+list(binaryOperators))
      self.comparison = "{} "+str(tokens[0])+" "+str(tokens[1])

   def type (self):
      return "goals"

   def tokens (self):
      return self.comparison.split(" ")[1:]

   def expression (self):
      return self.comparison

   def args (self, gamestate):
      return (gamestate.player_goals(self.pname,self.home),)

class EveryCondition (ArithCondition):
   desc = """Plays when the number of goals is divisible by the given number."""

   def __init__(self, tokens, **kwargs):
      super().__init__(**kwargs)
      self.comparison = "{} % "+tokens[0]+" == 0"
      self.num = tokens[0]

   def type (self):
      return "every"

   def tokens (self):
      return [str(self.num)]

   def args (self, gamestate):
      return (gamestate.player_goals(self.pname,self.home),)

   def expression(self):
      return self.comparison

class OpponentCondition (Condition):
   desc = """Plays when the opponent is one of the listed teams (separated by spaces, exclude slashes from ends)."""

   def __init__(self, tokens, **kwargs):
      super().__init__(**kwargs)
      self.others = []
      for token in tokens:
         if " " in token:
            self.others.extend(token.split())
         else:
            self.others.append(token)

   def check(self,gamestate):
      return gamestate.opponent_name(self.home) in self.others

   def type (self):
      return "opponent"

   def tokens (self):
      return self.others

class TeamGoalsCondition (GoalCondition):
   desc = """Plays if the total number of goals scored by this team meets the given condition."""

   def __init__ (self, **kwargs):
      super().__init__(**kwargs)

   def args (self, gamestate):
      return (gamestate.team_score(self.home),)

   def type (self):
      return "teamgoals"

class LeadCondition (GoalCondition):
   desc = """Plays if the goal difference (yourteam - theirteam) meets the given condition."""

   def __init__ (self, **kwargs):
      # pass tokens up to GoalCondition, the only difference in handling is in args()
      try:
         super().__init__(**kwargs)
      except ValueError:
         raise ValueError("invalid LeadCondition operator "+tokens[0]+"; valid operators are "+list(binaryOperators))

   def args (self, gamestate):
      gd = gamestate.team_score(self.home) - gamestate.opponent_score(self.home)
      return (gd,)

   def type (self):
      return "lead"

   # other methods don't need to be implemented because they're the same as GoalCondition

class FirstCondition (Condition):
   desc = """Plays if this is the first goal that the team has scored in this match."""

   def __init__ (self, tokens, **kwargs):
      super().__init__(**kwargs)

   def check(self, gamestate):
      return gamestate.team_score(self.home) == 1

   def type (self):
      return "first"

   def tokens (self):
      return []

class ComebackCondition (Condition):
   desc = """Plays when the team was behind prior to this goal being scored. Equivalent to lead <= 0."""

   def __init__(self, tokens, **kwargs):
      super().__init__(**kwargs)

   def check(self,gamestate):
      return gamestate.team_score(self.home) <= gamestate.opponent_score(self.home) and gamestate.opponent_score(self.home) > 0

   def type (self):
      return "comeback"

   def tokens (self):
      return []

class MatchCondition (Condition):
   desc = """Plays if the match any of the listed types."""
   types = ["Group", "Survival", "RO16", "Quarterfinal", "Semifinal", "Final", "Third-Place", "Boss", "Consolation"]
   knockout = ["RO16", "Quarterfinal", "Semifinal", "Final", "Third-Place"]

   def __init__ (self, tokens, **kwargs):
      super().__init__(**kwargs)
      if len(tokens) == 1 and tokens[0].lower() == "knockouts":
         tokens = MatchCondition.knockout
      self.lst = set([x.lower() for x in tokens])

   def check (self, gamestate):
      return gamestate.gametype.lower() in self.lst

   def type (self):
      return "match"

   def tokens (self):
      return list(self.lst)

class HomeCondition (Condition):
   desc = """Plays if the team is at home. (Use 'not home' for away.)"""

   def __init__(self, tokens, **kwargs):
      super().__init__(**kwargs)

   def check (self, gamestate):
      return self.home

   def type (self):
      return "home"

   def tokens (self):
      return []

class OnceCondition (Condition):
   desc = """Plays this song exactly once."""

   def __init__(self, tokens, **kwargs):
      super().__init__(**kwargs)
      self.okay = True

   def check (self, gamestate):
      if self.okay:
         self.okay = False
         return True
      raise UnloadSong

   def type (self):
      return "once"

   def tokens (self):
      return []

class MostGoalsCondition (Condition):
   desc = """Plays when either this player, or the specified player, has scored the most goals for this team in the match."""

   def __init__(self, tokens, pname=None, **kwargs):
      if len(tokens) > 0:
         super().__init__(pname=tokens[0],**kwargs)
         self.specified = tokens[0]
      else:
         super().__init__(pname=pname,**kwargs)
         self.specified = None

   def check (self, gamestate):
      scorers = gamestate.team_scorers(self.home)
      mygoals = gamestate.player_goals(self.pname,self.home)
      for player in scorers:
         if mygoals < scorers[player]:
            return False
      return True

   def tokens (self):
      if self.specified is None:
         return []
      else:
         return [self.specified]

   def type (self):
      return "mostgoals"

class SpecialCondition (Condition):
   desc = """(DO NOT SET THIS CONDITION UNDER ANYTHING ELSE OTHER THAN VICTORY ANTHEM, IT WILL BREAK YOUR .4CCM)

Used to allow easy access to special victory anthems on Rigdio. Change the label below if you wish to give this a custom name (default is song's filename)."""

   def __init__(self, tokens, **kwargs):
      if len(tokens) > 0:
         self.label = tokens[0]
      else:
         self.label = ""

   def check (self, gamestate):
      return False

   def type (self):
      return "special"

   def tokens (self):
      return [self.label]


class PromptCondition (Condition):
   def __init__ (self, dtype, **kwargs):
      super().__init__(**kwargs)
      self.dtype = dtype

   def check (self, gamestate):
      if self.needsPrompt(gamestate):
         dialog = self.dtype(gamestate.instance)
         results = dialog.results
         return self.checkResults(gamestate,results)
      else:
         return self.checkStored(gamestate)

class TimeCondition (PromptCondition):
   class Prompt (Dialog):
      def __init__ (self, *args, **kwargs):
         super().__init__(*args, **kwargs)

      def body (self, frame):
         Label(frame,text="When was the goal scored (minute)?").pack()
         self.inputVar = StringVar()
         entry = Entry(frame,textvariable=self.inputVar)
         entry.pack()
         entry.focus()

      def validate (self):
         try:
            int(self.inputVar.get())
         except:
            messagebox.showwarning("Input Error", "Goal time must be an integer.")
            return False
         return True

      def apply (self):
         self.results = [int(self.inputVar.get())]

   def __init__ (self, tokens, **kwargs):
      super().__init__(dtype=TimeCondition.Prompt,**kwargs)
      if tokens[0] == "=":
         tokens[0] = "=="
      if tokens[0] not in binaryOperators:
         raise ValueError("invalid GoalCondition operator "+tokens[0]+"; valid operators are "+list(binaryOperators))
      self.operator = tokens[0]
      try:
         self.time = int(tokens[1])
      except:
         raise ValueError("Invalid TimeCondition token {}; must be integer.".format(tokens[1]))

   def needsPrompt (self, gamestate):
      return gamestate.time == None

   def checkResults (self, gamestate, results):
      # remove the song from the list if it's later in the game, to save ram from shit like /remi/
      gamestate.time = results[0]
      return self.checkStored(gamestate)

   def checkStored (self, gamestate):
      if gamestate.time > self.time and self.operator in unloadableOperators:
         raise UnloadSong
      return eval("{} {} {}".format(gamestate.time, self.operator, self.time))

   def type (self):
      return "time"

   def tokens (self):
      return [self.operator, str(self.time)]

class MetaCondition (Condition):
   def __init__ (self, tokens, **kwargs):
      super().__init__(**kwargs)
      if isinstance(tokens, dict):
         self.sub = []

      elif isinstance(tokens, list): # deprecated, will be removed for later conditions
         self.sub = []
         temp = (" ".join(tokens)).split(",")
         for item in temp:
            self.sub.append(buildCondition(pname=self.pname,tname=self.tname,tokens=item.split(" "),home=self.home))

   def tokens (self):
      result = ",".join([str(x) for x in self.subconditions()])
      return result.split(" ")

   def subconditions (self):
      return self.sub

   def toYML (self):
      output = {self.type():[]}
      for item in self.subconditions():
         output[self.type()].append(item.toYML())
      return output

class NotCondition (MetaCondition):
   desc = """True when the given condition is false."""

   def __init__(self, tokens, condition = None, **kwargs):
      if condition is not None:
         kwargs["tokens"] = [condition.type, *condition.tokens()]
         home = condition.home
      super().__init__(tokens=tokens,**kwargs)

   def type (self):
      return "not"

   def check(self, gamestate):
      return not self.subconditions()[0].check(gamestate)

class OrCondition (MetaCondition):
   desc = """True when one of the given conditions is true."""

   def type (self):
      return "or"

   def check(self, gamestate):
      for condition in self.subconditions():
         if condition.check(gamestate):
            return True
      return False

class AndCondition (MetaCondition):
   desc = """True when all of the given conditions are true. This is the default ConditionList behaviour, but can be used inside other MetaConditions."""

   def type (self):
      return "and"

   def check (self, gamestate):
      for condition in self.subconditions():
         if not condition.check(gamestate):
            return False
      return True

class IfCondition (MetaCondition):
   desc = """Contains three conditions: if the first condition is True, checks the second condition; otherwise checks the third."""

   def type (self):
      return "if"

   def check (self, gamestate):
      first = self.subconditions()[0].check(gamestate)
      if first:
         return self.subconditions()[1].check(gamestate)
      else:
         return self.subconditions()[2].check(gamestate)

class Instruction:
   """
      Class used for something which modifies a ConditionPlayer rather than determining when it will play.

      This is a purely internal distinction; Instruction and Condition objects are manipulated and created the same ways by editing files or using rigDJ.
   """
   def isInstruction (self):
      return True

   def append (self, player):
      """
         Registers this instruction to the start, end, or pause instruction list.
      """
      raise NotImplementedError("Instruction subclass must override append().")

   def prep (self, player):
      """
         Prepares this instruction for later use.
      """
      raise NotImplementedError("Instruction subclass must override prep().")

   def run (self, player):
      """
         Applies this instruction to a given media player object.
      """
      raise NotImplementedError("Instruction subclass must override run().")

   def __str__ (self):
      return "{} {}".format(self.type()," ".join(self.tokens())).strip()

   def __repr__ (self):
      #return "buildCondition(pname={},tname={},home={},tokens={})".format(self.pname,self.tname,self.home,str(self).split(" "))
      return "buildCondition(tokens={})".format(str(self).split(" "))

   def type (self):
      raise NotImplementedError("Instruction subclass must override type().")

   def tokens (self):
      """
         Gives this Instruction as a list of tokens, EXCLUDING the type of the condition.

         In essence, these are the tokens passed to the constructor.
      """
      raise NotImplementedError("Instruction subclass must override tokens().")

   def toYML (self):
      tokens = self.tokens()
      if len(tokens) == 0:
         tokens = None
      elif len(tokens) == 1:
         tokens = tokens[0]
      return {self.type() : tokens}

   def allowUnloaded (self):
      return False

class StartInstruction (Instruction):
   desc = """Starts the file at the given time (in min:sec format)."""

   def __init__ (self, tokens, **kwargs):
      timestring = tokens[0]
      self.rawTime = timestring
      self.startTime = int(1000*timeToSeconds(timestring))

   def append (self, player):
      player.instructionsStart.append(self)

   def prep (self, player):
      player.startTime = self.startTime

   def run (self, player):
      player.song.time_pos = self.startTime / 1000.0

   def type (self):
      return "start"

   def tokens(self):
      return [self.rawTime]

class SpeedInstruction (Instruction):
   desc = """Plays the file at the given playback speed (from 0.25 to 4.00 with 1.00 being regular speed, anything outside the range won't work)."""

   def __init__ (self, tokens, **kwargs):
      speedstring = tokens[0]
      self.rawSpeed = speedstring
      self.playbackSpeed = float(speedstring)

   def append (self, player):
      player.instructionsStart.append(self)

   def prep (self, player):
      player.customSpeed = True

   def run (self, player):
      player.song.speed = self.playbackSpeed

   def type (self):
      return "speed"

   def tokens(self):
      return [self.rawSpeed]

class RandomiseInstruction (Instruction):
   desc = """If all songs for a single player have this condition, Rigdio will randomly pick and play a song from the list everytime instead of following priority."""

   def __init__ (self, tokens, **kwargs):
      pass

   def append (self, player):
      player.instructionsStart.append(self)

   def prep (self, player):
      player.randomise = True

   def run (self, player):
      pass

   def type (self):
      return "randomise"

   def tokens(self):
      return []

class PauseInstruction (Instruction):
   desc = """Specify action taken when goalhorn is paused."""
   types = ["continue", "restart"]

   def __init__ (self, tokens, **kwargs):
      self.every = 1
      if tokens[0] not in PauseInstruction.types:
         raise ValueError("Unrecognised pause type (allowed values: {}).".format(", ".join(PauseInstruction.types)))
      if len(tokens) > 1:
         if tokens[1] == "every":
            self.every = int(tokens[2])
      self.command = tokens[0]

   def append (self, player):
      player.instructionsPause.append(self)

   def prep (self, player):
      self.played = 0

   def run (self, player):
      self.played += 1
      if self.command == "continue":
         return
      if self.played % self.every == 0:
         if self.command == "restart":
            player.song.time_pos = player.startTime / 1000.0

   def type (self):
      return "pause"

   def tokens (self):
      return [self.command]

class EndInstruction (Instruction):
   desc = (
      "Specify action taken when goalhorn reaches the end.\n"
      "Goalhorns loop by default."
   )
   types = ["stop"]

   def __init__ (self, tokens, **kwargs):
      if tokens[0] == "loop":
         # ;end loop is a no-op: goalhorns loop by default, and this
         # instruction previously spawned a useless endChecker thread
         # that prevented rigdio from closing cleanly.
         # Silently ignore it for backwards compatibility with old 4ccm files.
         print("Ignoring ';end loop' instruction (goalhorns loop by default).")
         self.command = "loop"
         return
      if tokens[0] not in EndInstruction.types:
         raise ValueError("Unrecognised end type (allowed values: {}).".format(", ".join(EndInstruction.types)))
      self.command = tokens[0]

   def append (self, player):
      if self.command != "stop":
         return
      player.instructionsEnd.append(self)

   def prep (self, player):
      if self.command == "stop":
         player.repeat = False

   def run (self, playerManager):
      if self.command == "stop":
         playerManager.song.reloadSong()

   def type (self):
      return "end"

   def tokens(self):
      return [self.command]

class WarcryInstruction (Instruction):
   desc = """Play next song that doesn't have this instruction in priority list once this ends, meant to be short like a war cry."""

   def __init__ (self, tokens, **kwargs):
      pass

   def append (self, player):
      player.instructionsEnd.append(self)

   def prep (self, player):
      # if for some reason the warcry is set to loop, turn it off
      player.repeat = False
      player.warcry = True

   def run (self, playerManager):
      # runs when the warcry ends, to let PlayerManager know to play a non-warcry song now
      playerManager.warcry = False
      playerManager.playSong()

   def type (self):
      return "warcry"

   def tokens(self):
      return []

class UnrandomInstruction (Instruction):
   desc = """Exclude song from randomised playbacks. Only works on chants."""

   def __init__ (self, tokens, **kwargs):
      pass

   def append (self, player):
      player.instructionsStart.append(self)

   def prep (self, player):
      pass

   def run (self, player):
      pass

   def type (self):
      return "unrandom"

   def tokens(self):
      return []

class LouderInstruction (Instruction):
   desc = """Marks this track for volume boosting. When normalization is enabled, a Volume Boost slider will appear for the team, and its value will be added to the master volume for this track."""

   def __init__ (self, tokens, **kwargs):
      pass

   def append (self, player):
      player.instructionsStart.append(self)

   def prep (self, player):
      player.louder = True

   def run (self, player):
      pass

   def type (self):
      return "louder"

   def tokens(self):
      return []

class AdvanceInstruction (Instruction):
   desc = """When this song ends, play the next valid goalhorn instead of looping or stopping."""

   def __init__ (self, tokens, **kwargs):
      pass

   def append (self, player):
      player.instructionsEnd.append(self)

   def prep (self, player):
      player.repeat = False

   def run (self, playerManager):
      playerManager.playSong(skip=playerManager.song)

   def type (self):
      return "advance"

   def tokens(self):
      return []

class EventInstruction (Instruction):
   desc = """DEPRECATED: PLEASE USE EVENT: IN YOUR .YML"""
   types = ["red", "yellow", "owngoal", "sub"]

   def __init__ (self, tokens, **kwargs):
      if tokens[0] not in EventInstruction.types:
         raise ValueError("Unrecognised event type (allowed values: {}).".format(", ".join(EventInstruction.types)))
      self.etype = tokens[0]

   def append (self, player):
      player.instructionsStart.append(self)

   def prep (self, player):
      player.event = self.etype
      player.repeat = False

   def run (self, player):
      pass

   def type (self):
      return "event"

   def tokens(self):
      return [self.etype]

   def allowUnloaded (self):
      return True

conditions = {
   "goals" : GoalCondition,
   "teamgoals" : TeamGoalsCondition,
   "lead" : LeadCondition,
   "opponent" : OpponentCondition,
   "match" : MatchCondition,
   "home" : HomeCondition,
   "once" : OnceCondition,
   "mostgoals" : MostGoalsCondition,
   "special" : SpecialCondition,
   "every" : EveryCondition,
   "comeback" : ComebackCondition,
   "first" : FirstCondition,
   # meta
   "not" : NotCondition,
   #"or" : OrCondition,
   #"and" : AndCondition,
   #"if" : IfCondition,
   # instruction; now separate, only here for legacy support
   "start" : StartInstruction,
   "speed" : SpeedInstruction,
   "randomise" : RandomiseInstruction,
   "pause" : PauseInstruction,
   "end" : EndInstruction,
   "warcry" : WarcryInstruction,
   "unrandom" : UnrandomInstruction,
   "advance" : AdvanceInstruction,
   "louder" : LouderInstruction,
   "event" : EventInstruction # deprecated, for .4ccm use
}

instructions = {
   "start" : StartInstruction,
   "speed" : SpeedInstruction,
   "randomise" : RandomiseInstruction,
   "pause" : PauseInstruction,
   "end" : EndInstruction,
   "warcry" : WarcryInstruction,
   "unrandom" : UnrandomInstruction,
   "advance" : AdvanceInstruction,
   "louder" : LouderInstruction
}

def processTokens (tokenStr):
   data = tokenStr.split()
   i = 0
   while i < len(data):
      # escape character
      if data[i][0] == "\\":
         data[i] = data[i][1:]
      # quoted string semantics
      elif data[i][0] == "[":
         data[i] = list(data[i])
         while data[i+1][-1] != "]" or data[i+1][-2] == "\\":
            temp = list(data.pop(i+1))
            # remove escapes on end of string
            if temp[-1] == "]" and temp[-2] == "\\":
               temp.pop(-2)
            data[i].append(" ")
            data[i].extend(temp)
         data[i].append(" ")
         data[i].extend(list(data.pop(i+1)))
         data[i] = "".join(data[i][1:-1]) # remove the []
      i += 1
   return data

def buildCondition(tokens, **kwargs):
   if len(tokens) == 0:
      return None # empty token list
   try:
      return conditions[tokens[0].lower()](tokens=tokens[1:],**kwargs)
   except KeyError:
      raise ValueError("condition/instruction {} not recognised.".format(tokens[0]))

class ConditionList:
   def buildCondition(tokens, **kwargs):
      if len(tokens) == 0:
         return None # empty token list
      try:
         return conditions[tokens[0].lower()](tokens=tokens[1:],**kwargs)
      except KeyError:
         raise ValueError("condition/instruction {} not recognised.".format(tokens[0]))

   def __init__(self, pname = "NOPLAYER", tname = "NOTEAM", data = [], songname = "New Song", home = True):
      self.pname = pname
      self.tname = tname
      self.home = home
      self.songname = songname
      self.conditions = []
      self.instructions = []
      self.disabled = False
      self.startTime = 0
      self.endType = "loop"
      self.pauseType = "continue"
      for tokenStr in data:
         tokens = processTokens(tokenStr)
         condition = ConditionList.buildCondition(tokens, pname=self.pname, tname=self.tname, home=self.home)
         if condition.isInstruction():
            self.instructions.append(condition)
         else:
            self.conditions.append(condition)
      self.all = self.conditions + self.instructions

   def __str__(self):
      output = "{}".format(basename(self.songname))
      for condition in self.conditions:
         output = output + ";" + str(condition)
      for instruction in self.instructions:
         output = output + ";" + str(instruction)
      return output
   __repr__ = __str__

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

class InstructionList:
   def __init__ (self, raw):
      self.instructions = []
      for instruction in raw:
         if not isinstance(instruction,dict):
            print("ERROR: condition list entry must be dict, got {}.".format(type(instruction)))
         if len(instruction.keys()) > 1:
            print("WARNING: multiple keys in condition entry. Did you forget a - at the beginning of a line?")
         key = None
         for temp in instruction.keys():
            key = temp
            break
         condType = instructions[key.lower()]
         self.instructions.append(condType(tokens=instruction[key] if isinstance(instruction[key],list) else [instruction[key]]))