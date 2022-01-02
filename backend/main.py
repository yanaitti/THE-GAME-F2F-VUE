
from flask import Flask, Response, render_template, url_for
from flask_caching import Cache
import uuid
import random
import collections
import json
import os
import copy

app = Flask(__name__, static_folder='../dist/static', template_folder='../dist')

@app.context_processor
def override_url_for():
    return dict(url_for=dated_url_for)


def dated_url_for(endpoint, **values):
    if endpoint == 'static':
        filename = values.get('filename', None)
        if filename:
            file_path = os.path.join(app.root_path,
                                     endpoint, filename)
            values['q'] = int(os.stat(file_path).st_mtime)
    return url_for(endpoint, **values)


@app.after_request
def add_header(r):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to cache the rendered page for 10 minutes.
    """
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    r.headers['Cache-Control'] = 'public, max-age=0'
    return r

# Cacheインスタンスの作成
cache = Cache(app, config={
    'CACHE_TYPE': 'redis',
    'CACHE_REDIS_URL': os.environ.get('REDIS_URL', 'redis://localhost:6379'),
    'CACHE_DEFAULT_TIMEOUT': 60 * 60 * 2,
})


@app.route('/')
def index():
    return render_template('index.html')


# create the game group
@app.route('/create/<nickname>')
def create_game(nickname):
    game = {
        'status': 'waiting',
        'routeidx': 0,
        'players': []}
    player = {}

    gameid = str(uuid.uuid4())
    game['gameid'] = gameid
    player['playerid'] = gameid
    player['nickname'] = nickname
    player['holdcards'] = []
    player['stocks'] = list(range(2, 60))
    game['2picks'] = True # 2枚取得フラグ True...2枚, False...6枚
    game['players'].append(player)

    app.logger.debug(gameid)
    app.logger.debug(game)
    cache.set(gameid, game)
    return gameid


# re:wait the game
@app.route('/<gameid>/waiting')
def waiting_game(gameid):
    game = cache.get(gameid)
    game['status'] = 'waiting'
    cache.set(gameid, game)
    return 'reset game status'


@app.route('/<gameid>/join')
def invited_join_game(gameid):
    print('gameid:' + gameid)
    return render_template('index.html', gameid=gameid)


# join the game
@app.route('/<gameid>/join/<nickname>')
def join_game(gameid, nickname='default'):
    game = cache.get(gameid)
    if game['status'] == 'waiting':
        player = {}

        playerid = str(uuid.uuid4())
        player['playerid'] = playerid
        if nickname == 'default':
            player['nickname'] = playerid
        else:
            player['nickname'] = nickname
        player['holdcards'] = []
        player['stocks'] = list(range(2, 60))
        game['players'].append(player)

        cache.set(gameid, game)
        return playerid + ' ,' + player['nickname'] + ' ,' + game['status']
    else:
        return 'Already started'


# processing the game
@app.route('/<gameid>/start')
@app.route('/<gameid>/start/<rule_type>')
def start_game(gameid, rule_type=''):
    game = cache.get(gameid)
    app.logger.debug(gameid)
    app.logger.debug(game)
    game['status'] = 'started'
    # game['stocks'] = list(range(2, 59))
    game['submit'] = []
    game['rule'] = rule_type
    game['2picks'] = True

    # playerids = [player['playerid'] for player in game['players']]
    routelist = copy.copy(game['players'])
    random.shuffle(routelist)
    game['routelist'] = routelist

    players = game['players']

    for player in players:
        player['holdcards'] = []
        while len(player['holdcards']) < 6:
            player['holdcards'].append(player['stocks'].pop(random.randint(0, len(player['stocks']) - 1)))

    game['hightolow'] = []
    game['lowtohigh'] = []
    game['hightolow'].append([60])
    game['hightolow'].append([60])
    game['lowtohigh'].append([1])
    game['lowtohigh'].append([1])

    cache.set(gameid, game)
    return json.dumps(game['routelist'])


# next to player the game
@app.route('/<gameid>/next/<clientid>')
def processing_game(gameid, clientid):
    game = cache.get(gameid)

    game['routeidx'] = (game['routeidx'] + 1) % len(game['players'])
    player = [player for player in game['players'] if player['playerid'] == clientid][0]

    if game['2picks']: # 自分の場のみ出したとき
        for idx in range(2):
            if len(player['stocks']) > 0 and len(player['holdcards']) < 6:
                player['holdcards'].append(player['stocks'].pop(random.randint(0, len(player['stocks']) - 1)))
            else:
                continue
    else: # 相手の場にも出したとき
        while len(player['holdcards']) < 6:
            if len(player['stocks']) > 0:
                player['holdcards'].append(player['stocks'].pop(random.randint(0, len(player['stocks']) - 1)))
            else:
                continue

    game['2picks'] = True
    game['submit'] = []

    cache.set(gameid, game)
    return 'go on to the next user'


# set the card on the line

@app.route('/<gameid>/<clientid>/set/<int:lineid>/<int:cardnum>')
def setcard_game(gameid, clientid, lineid, cardnum):
    game = cache.get(gameid)
    player = [player for player in game['players'] if player['playerid'] == clientid][0]
    isHit = False

    if lineid in [0, 1]:
        highToLow = game['hightolow'][lineid]
        # 100 -> 2
        if highToLow[-1] > cardnum:
            # highToLow.append(cardnum)
            isHit = True
        if (highToLow[-1] + 10) == cardnum and isHit == False:
            # highToLow.append(cardnum)
            isHit = True
        # if game['rule'] == 'original' and isHit == False:
        #     if len(str(cardnum)) > 1 and len(str(highToLow[-1])) > 1:
        #         cardnum_str = str(cardnum)
        #         latest_str = str(highToLow[-1])
        #         if cardnum_str[0] == cardnum_str[1] and latest_str[0] == latest_str[1]:
        #             # highToLow.append(cardnum)
        #             isHit = True
        #     if highToLow[-1] % 10 == cardnum % 10:
        #         # highToLow.append(cardnum)
        #         isHit = True
        if isHit == False:
            return 'Error1'
        else:
            highToLow.append(cardnum)
    elif lineid in [2, 3]:
        lowToHigh = game['lowtohigh'][lineid%2]
        # 1 -> 99
        if lowToHigh[-1] < cardnum:
            # lowToHigh.append(cardnum)
            isHit = True
        if (lowToHigh[-1] - 10) == cardnum and isHit == False:
            # lowToHigh.append(cardnum)
            isHit = True
        # if game['rule'] == 'original' and isHit == False:
        #     if len(str(cardnum)) > 1 and len(str(lowToHigh[-1])) > 1:
        #         cardnum_str = str(cardnum)
        #         latest_str = str(lowToHigh[-1])
        #         if cardnum_str[0] == cardnum_str[1] and latest_str[0] == latest_str[1]:
        #             # lowToHigh.append(cardnum)
        #             isHit = True
        #     if lowToHigh[-1] % 10 == cardnum % 10:
        #         # lowToHigh.append(cardnum)
        #         isHit = True
        if isHit == False:
            return 'Error2'
        else:
            lowToHigh.append(cardnum)
    else:
        return 'Error'

    if gameid == clientid:
        if lineid in [1, 3]:
            game['2picks'] = False
    else:
        if lineid in [0, 2]:
            game['2picks'] = False

    game['submit'].append(cardnum)
    player['holdcards'].remove(cardnum)

    cache.set(gameid, game)
    return 'ok'


# all status the game
@app.route('/<gameid>/status')
def game_status(gameid):
    game = cache.get(gameid)

    return json.dumps(game)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
