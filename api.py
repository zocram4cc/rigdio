from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import os
from rigparse import parse
from audio_manager import audio_manager
from gamestate import GameState
import logging

# Global GameState object
gamestate = GameState()

# Custom logging configuration
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
        },
        "file": {
            "formatter": "default",
            "class": "logging.FileHandler",
            "filename": "api.log",
        },
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["default", "file"],
            "level": "INFO",
        },
        "uvicorn.error": {
            "level": "INFO",
        },
        "uvicorn.access": {
            "level": "INFO",
        },
    },
}
logging.basicConfig(level=logging.DEBUG)



app = FastAPI()

class LoadRequest(BaseModel):
    home: str
    away: str
    match_type: str | None = None

@app.post("/api/load")
async def load_teams(request: LoadRequest):
    logging.info(f"Received /api/load request with home='{request.home}', away='{request.away}', and match_type='{request.match_type}'")
    home_team_id = request.home
    away_team_id = request.away

    if request.match_type:
        gamestate.gametype = request.match_type
    else:
        gamestate.gametype = None

    # Assuming music is in 'music/<team_id>/<team_id>.4ccm'
    home_path = os.path.join("music", home_team_id, f"{home_team_id}.4ccm")
    away_path = os.path.join("music", away_team_id, f"{away_team_id}.4ccm")

    if not os.path.exists(home_path):
        logging.error(f"Home team file not found: {home_path}")
        raise HTTPException(status_code=404, detail=f"Home team file not found: {home_path}")
    if not os.path.exists(away_path):
        logging.error(f"Away team file not found: {away_path}")
        raise HTTPException(status_code=404, detail=f"Away team file not found: {away_path}")

    home_music, home_name, _ = parse(home_path, load=False, home=True)
    away_music, away_name, _ = parse(away_path, load=False, home=False)

    # Manually add generic goal horn to each player
    if 'goal' in home_music:
        for name, conditions in home_music.items():
            if name not in ['anthem', 'victory', 'goal', 'name', 'chant', ';event']:
                conditions.extend(home_music['goal'])
    
    if 'goal' in away_music:
        for name, conditions in away_music.items():
            if name not in ['anthem', 'victory', 'goal', 'name', 'chant', ';event']:
                conditions.extend(away_music['goal'])

    audio_manager.home_team = home_name
    audio_manager.away_team = away_name
    audio_manager.home_music = home_music
    audio_manager.away_music = away_music
    audio_manager.clear_goalhorn_positions()

    gamestate.clear()
    gamestate.home_name = home_name
    gamestate.away_name = away_name

    logging.info(f"Loaded music for home team '{home_name}' and away team '{away_name}'")
    return {"message": f"Loaded music for home team '{home_name}' and away team '{away_name}'"}

@app.post("/api/anthems")
async def play_anthems():
    logging.info("Received /api/anthems request")
    audio_manager.play_anthems(gamestate)
    return {"message": "Playing anthems"}

class VictoryRequest(BaseModel):
    team: str

@app.post("/api/victory")
async def play_victory(request: VictoryRequest):
    logging.info(f"Received /api/victory request for team {request.team}")
    audio_manager.play_victory_anthem(request.team)
    return {"message": f"Playing victory anthem for {request.team}"}

@app.post("/api/warcry")
async def play_warcry():
    logging.info("Received /api/warcry request")
    audio_manager.play_warcry()
    return {"message": "Playing warcry"}

class GoalRequest(BaseModel):
    team: str
    scorer: str

@app.post("/api/goal")
async def play_goal(request: GoalRequest):
    logging.info(f"Received /api/goal request for team {request.team} and scorer {request.scorer}")
    home_team = request.team == "home"
    gamestate.score(request.scorer, home_team)
    audio_manager.play_goal_sound(request.team, request.scorer, gamestate)
    return {"message": f"Playing goal sound for {request.scorer}"}

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=31338, reload=True, log_config=LOGGING_CONFIG)
