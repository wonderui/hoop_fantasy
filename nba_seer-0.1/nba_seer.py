# import modules ----------------------

import nba_py
import nba_py.game
import nba_py.player
import nba_py.team

import pandas as pd
import numpy as np

import datetime
import pytz

old_settings = np.seterr(all='print')
np.geterr()

print('modules imported')


# define functions ----------------------

def get_games(date):
    """
    :param date: datetime.date, the match day
    :return: df, all the games on the given day
    """
    return nba_py.Scoreboard(month=date.month,
                             day=date.day,
                             year=date.year,
                             league_id='00',
                             offset=0).game_header()[['GAME_ID', 'HOME_TEAM_ID', 'VISITOR_TEAM_ID']]


def get_players(games, all_players):
    """
    :param games: df, some games
    :param all_players: df, all players list of this season
    :return: df, all players of the given games
    """
    home_team_player = all_players[all_players['TEAM_ID'].isin(games['HOME_TEAM_ID'])][['PERSON_ID', 'TEAM_ID']]
    home_team_player['Location'] = 'HOME'
    away_team_player = all_players[all_players['TEAM_ID'].isin(games['VISITOR_TEAM_ID'])][['PERSON_ID', 'TEAM_ID']]
    away_team_player['Location'] = 'AWAY'
    players = pd.concat([home_team_player, away_team_player])
    game_team = pd.concat([games[['HOME_TEAM_ID', 'GAME_ID']].rename(columns={'HOME_TEAM_ID': 'TEAM_ID'}),
                           games[['VISITOR_TEAM_ID', 'GAME_ID']].rename(columns={'VISITOR_TEAM_ID': 'TEAM_ID'})])
    players = pd.merge(players, game_team, on='TEAM_ID')
    team_team = pd.concat(
        [games[['HOME_TEAM_ID', 'VISITOR_TEAM_ID']].rename(columns={'HOME_TEAM_ID': 'TEAM_ID',
                                                                    'VISITOR_TEAM_ID': 'Against_Team_ID'}),
         games[['VISITOR_TEAM_ID', 'HOME_TEAM_ID']].rename(columns={'VISITOR_TEAM_ID': 'TEAM_ID',
                                                                    'HOME_TEAM_ID': 'Against_Team_ID'})])
    players = pd.merge(players, team_team, on='TEAM_ID')
    players = pd.merge(players, all_players[['PERSON_ID', 'DISPLAY_FIRST_LAST', 'TEAM_ABBREVIATION']], on='PERSON_ID')
    return players


def get_players_p(games, game_stats_logs):
    """
    :param games: df, some games
    :param game_stats_logs: df, all previous game stats logs imported from sql
    :return: df, all players of the given games at the match date
    """
    players = pd.DataFrame()
    for i in games.index:
        players = players.append(game_stats_logs[(game_stats_logs['GAME_ID'] == games.iloc[i]['GAME_ID']) &
                                                 (game_stats_logs['TEAM_ID'] == games.iloc[i]['HOME_TEAM_ID'])])
        players = players.append(game_stats_logs[(game_stats_logs['GAME_ID'] == games.iloc[i]['GAME_ID']) &
                                                 (game_stats_logs['TEAM_ID'] == games.iloc[i]['VISITOR_TEAM_ID'])])

    players['Location'] = players.apply(lambda x: 'HOME' if x['TEAM_ID'] ==
                                                            int(games[games['GAME_ID'] == x['GAME_ID']]['HOME_TEAM_ID'])
    else 'AWAY', axis=1)

    team_team = pd.concat(
        [games[['HOME_TEAM_ID', 'VISITOR_TEAM_ID']].rename(columns={'HOME_TEAM_ID': 'TEAM_ID',
                                                                    'VISITOR_TEAM_ID': 'Against_Team_ID'}),
         games[['VISITOR_TEAM_ID', 'HOME_TEAM_ID']].rename(columns={'VISITOR_TEAM_ID': 'TEAM_ID',
                                                                    'HOME_TEAM_ID': 'Against_Team_ID'})])

    return pd.merge(players, team_team,
                    on='TEAM_ID')[['PLAYER_ID', 'TEAM_ID', 'Location', 'GAME_ID',
                                   'Against_Team_ID']].rename(columns={'PLAYER_ID': 'PERSON_ID'})


def get_last_n_game_logs(game_stats_logs, player_id, game_id, n):
    """
    :param game_stats_logs: df, all previous game stats logs imported from sql
    :param player_id: int, player id
    :param game_id: str, game id
    :param n: int, size of games
    :return: df, the n game log of the player before the given game
    """
    player_game_logs = game_stats_logs[game_stats_logs['PLAYER_ID'] == player_id]
    last_n_game = player_game_logs[player_game_logs['GAME_ID_O'] < game_id].sort_values('GAME_ID_O').tail(n)
    return last_n_game[['MINS', 'PTS', 'AST', 'OREB', 'DREB', 'STL', 'BLK', 'TO', 'FGM', 'FGA', 'FG3M']]


def get_score_36(game_logs):
    """
    :param game_logs: df, game logs
    :return: list, [0]the average fantasy score(int, 36mins) of the given game log, [1]the score cov(float) of the 
    given game log
    """
    convert_to_36 = lambda x: x[['PTS', 'AST', 'OREB', 'DREB', 'STL', 'BLK',
                                 'TO', 'FGM', 'FGA', 'FG3M']] * 36 / x['MINS']
    stats = game_logs.apply(convert_to_36, axis=1)
    stats['SCO'] = stats['PTS'] * 1 + stats['AST'] * 1.5 + stats['OREB'] * 1.2 + stats['DREB'] * 1.2 + \
        stats['STL'] * 2 + stats['BLK'] * 2 + stats['TO'] * -1
    stats['EFF'] = stats['SCO'] / 36
    stats = stats[abs(stats['EFF']) <= 2.5]
    return stats['SCO'].mean(), stats['SCO'].std() / stats['SCO'].mean()


def get_ma(game_stats_logs, row, n):
    """
    :param game_stats_logs: df, all previous game stats logs imported from sql
    :param row: pd.series, player id and game id
    :param n: int, size of ma
    :return: float, average fantasy score of the player in n games before the given game
    """
    player_id = row['PERSON_ID']
    game_id_o = row['GAME_ID'][3:5] + row['GAME_ID'][:3] + row['GAME_ID'][-5:]
    ma_n = get_score_36(get_last_n_game_logs(game_stats_logs, player_id, game_id_o, n))[0]
    return round(float(ma_n), 2)


def get_min(game_stats_logs, row, n):
    """
    :param game_stats_logs: df, all previous game stats logs imported from sql
    :param row: pd.series, player id and game id
    :param n: int, size of ma
    :return: float, average mins the player played in n games before the given game
    """
    player_id = row['PERSON_ID']
    game_id_o = row['GAME_ID'][3:5] + row['GAME_ID'][:3] + row['GAME_ID'][-5:]
    min_n = get_last_n_game_logs(game_stats_logs, player_id, game_id_o, n)['MINS'].mean()
    return round(float(min_n), 2)


def get_min_cov(game_stats_logs, row, n):
    """
    :param game_stats_logs: df, all previous game stats logs imported from sql
    :param row: pd.series, player id and game id
    :param n: int, size of ma
    :return: float, cov of mins the player played in n games before the given game
    """
    player_id = row['PERSON_ID']
    game_id_o = row['GAME_ID'][3:5] + row['GAME_ID'][:3] + row['GAME_ID'][-5:]
    min_cov_n = get_last_n_game_logs(game_stats_logs,
                                     player_id,
                                     game_id_o,
                                     n)['MINS'].std() / get_last_n_game_logs(game_stats_logs,
                                                                             player_id,
                                                                             game_id_o,
                                                                             n)['MINS'].mean()
    return round(float(min_cov_n), 3)


def get_sco_cov(game_stats_logs, row, n):
    """
    :param game_stats_logs: df, all previous game stats logs imported from sql
    :param row: pd.series, player id and game id
    :param n: int, size of ma
    :return: float, cov of scores the player get in n games before the given game
    """
    player_id = row['PERSON_ID']
    game_id_o = row['GAME_ID'][3:5] + row['GAME_ID'][:3] + row['GAME_ID'][-5:]
    sco_cov_n = get_score_36(get_last_n_game_logs(game_stats_logs, player_id, game_id_o, n))[1]
    return round(float(sco_cov_n), 3)


def last_n_games_days(game_stats_logs, row, n):
    """
    :param game_stats_logs: df, all previous game stats logs imported from sql
    :param row: pd.series, player id and game id
    :param n: int, size of the spread of games
    :return: int, the days last for last n games
    """
    player_id = row['PERSON_ID']
    game_id_o = row['GAME_ID'][3:5] + row['GAME_ID'][:3] + row['GAME_ID'][-5:]
    player_stats_logs = game_stats_logs[game_stats_logs['PLAYER_ID'] == player_id]
    ordered_logs = player_stats_logs.sort_values('GAME_ID_O')
    player_5g = ordered_logs[(ordered_logs['GAME_ID_O'] < game_id_o) &
                             (ordered_logs['MINS'].notnull())].tail(n)
    if len(player_5g) != 0:
        min_d = datetime.datetime.strptime(player_5g['GAME_DATE_EST'].min()[:10], '%Y-%m-%d').date()
        max_d = datetime.datetime.strptime(player_5g['GAME_DATE_EST'].max()[:10], '%Y-%m-%d').date()
        return (max_d - min_d).days + 1
    else:
        return None


def days_rest(game_stats_logs, row):
    """
    :param game_stats_logs: df, all previous game stats logs imported from sql
    :param row: pd.series, player id and game id
    :return: int, the days player have rest till this game
    """
    player_id = row['PERSON_ID']
    game_id_o = row['GAME_ID'][3:5] + row['GAME_ID'][:3] + row['GAME_ID'][-5:]
    player_stats_logs = game_stats_logs[game_stats_logs['PLAYER_ID'] == player_id]
    ordered_logs = player_stats_logs.sort_values('GAME_ID_O')
    last_game = ordered_logs[(ordered_logs['GAME_ID_O'] < game_id_o) &
                             (ordered_logs['MINS'].notnull())].tail(1)
    if len(last_game) != 0:
        last_g_d = datetime.datetime.strptime(last_game['GAME_DATE_EST'].max()[:10], '%Y-%m-%d').date()
        ustz = pytz.timezone('America/New_York')
        us_time = datetime.datetime.now(ustz)
        today = us_time.date()
        return (today - last_g_d).days - 1
    else:
        return None


def location_aff(game_stats_logs, row):
    """
    :param game_stats_logs: df, all previous game stats logs imported from sql
    :param row: pd.series, player id and game id
    :return: list, [0]home game affection, [1] away game affection
    """
    player_id = row['PERSON_ID']
    game_id_o = row['GAME_ID'][3:5] + row['GAME_ID'][:3] + row['GAME_ID'][-5:]
    player_stats_logs = game_stats_logs[game_stats_logs['PLAYER_ID'] == player_id].sort_values('GAME_ID_O')
    player_stats_home = player_stats_logs[(player_stats_logs['LOCATION'] == 'HOME') &
                                          (player_stats_logs['MINS'].notnull()) &
                                          (player_stats_logs['GAME_ID_O'] < game_id_o)].tail(20)
    home_score_20 = get_score_36(player_stats_home)[0]
    player_stats_away = player_stats_logs[(player_stats_logs['LOCATION'] == 'AWAY') &
                                          (player_stats_logs['MINS'].notnull()) &
                                          (player_stats_logs['GAME_ID_O'] < game_id_o)].tail(20)
    away_score_20 = get_score_36(player_stats_away)[0]
    player_stats_all = player_stats_logs[(player_stats_logs['MINS'].notnull()) &
                                         (player_stats_logs['GAME_ID_O'] < game_id_o)].tail(40)
    recent_score_40 = get_score_36(player_stats_all)[0]
    return home_score_20 / recent_score_40, away_score_20 / recent_score_40


def get_exp_sco(players, game_stats_logs):
    """
    :param players: df, players list
    :param game_stats_logs: df, all previous game stats logs imported from sql
    :return: df, all players with their expect fantasy score
    """
    players['5_g_d'] = players.apply(lambda x: last_n_games_days(game_stats_logs, x, 5), axis=1)
    print('5games days complete!')
    players['d_rest'] = players.apply(lambda x: days_rest(game_stats_logs, x), axis=1)
    print('days rest complete!')
    players['MA_20'] = players.apply(lambda x: get_ma(game_stats_logs, x, 20), axis=1)
    print('ma20 complete!')
    players['MA_10'] = players.apply(lambda x: get_ma(game_stats_logs, x, 10), axis=1)
    print('ma10 complete!')
    players['MA_5'] = players.apply(lambda x: get_ma(game_stats_logs, x, 5), axis=1)
    print('ma5 complete!')
    players['MIN_20'] = players.apply(lambda x: get_min(game_stats_logs, x, 20), axis=1)
    print('min20 complete!')
    players['MIN_10'] = players.apply(lambda x: get_min(game_stats_logs, x, 10), axis=1)
    print('min10 complete!')
    players['MIN_5'] = players.apply(lambda x: get_min(game_stats_logs, x, 5), axis=1)
    print('min5 complete!')
    players['MIN_COV_20'] = players.apply(lambda x: get_min_cov(game_stats_logs, x, 20), axis=1)
    print('min_cov_20 complete!')
    players['SCO_COV_20'] = players.apply(lambda x: get_sco_cov(game_stats_logs, x, 20), axis=1)
    print('sco_cov_20 complete!')
    players = players[players['SCO_COV_20'] > 0].copy()
    print('sco cov less than 0 droped!')
    players['home_aff'] = players.apply(lambda x: location_aff(game_stats_logs, x)[0], axis=1)
    players['away_aff'] = players.apply(lambda x: location_aff(game_stats_logs, x)[1], axis=1)
    print('location affect complete!')

    players['EXP_SCO'] = round(players[['MA_20', 'MA_10', 'MA_5']].mean(axis=1) *
                               players[['MIN_20', 'MIN_10', 'MIN_5']].mean(axis=1) / 36, 2)
    players['EXP_SCO_L'] = players.apply(lambda x: x['EXP_SCO'] * x['home_aff'] if x['Location'] == 'HOME'
    else x['EXP_SCO'] * x['away_aff'], axis=1)
    print('all done!')
    return players


print('functions defined')
