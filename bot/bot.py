import os
import re
import json

import requests
import telebot
from bs4 import BeautifulSoup
from raven import Client
from google_measurement_protocol import event, report

import amalgama
import lyrics as minilyrics
from acr_cloud import ACRCloud
from dotenv import load_dotenv
load_dotenv()

client = Client(os.environ.get('SENTRY'))

bot = telebot.TeleBot(os.environ.get('TELEGRAM_TOKEN_TEST_AUD'))
error = 'Could not find lyrics.'

ACR_access_key = os.environ.get('ACR_ACCESS_KEY')
ACR_access_secret = bytes(os.environ.get('ACR_ACCESS_SECRET'), 'utf-8')
acr = ACRCloud('eu-west-1.api.acrcloud.com', ACR_access_key, ACR_access_secret)

ANALYTICS_ACCOUNT_ID = os.environ.get('ANALYTICS_ACCOUNT_ID')
ANALYTICS_TRACKING_ID = os.environ.get('ANALYTICS_TRACKING_ID')


def handle_request(user):
    client.user_context({'id': user.id, 'username': user.username})


def get_genres(data):
    for music_list in data["metadata"]["music"]:
        for music_metadata in music_list:
            if music_metadata == "genres":
                genres = music_list[music_metadata][0]["name"]
                return genres


def get_youtube(artist, song):
    text = requests.get(f"https://www.youtube.com/results?search_query={artist} {song}").text
    soup = BeautifulSoup(text, "html.parser")
    yid = soup.find('a', href=re.compile('/watch'))['href']
    li = soup.find('ul', {'class': 'yt-lockup-meta-info'}).contents[1].text
    views = int(''.join(filter(str.isdigit, li)))
    if views > 100000:
        return f'https://www.youtube.com{yid}'


def media(data, keys):
    for i in data['metadata']['music']:
        for key, value in i['external_metadata'].items():
            if keys == 'youtube' == key:
                yid = value['vid']
                return yid
            if keys == 'deezer' == key:
                did = value['track']['id']
                return did
            if keys == 'spotify' == key:
                sid = value['track']['id']
                return sid


def musixmatch(artist, song):
    try:
        searchurl = f"https://www.musixmatch.com/search/{artist}-{song}/tracks"
        header = {"User-Agent": "curl/7.9.8 (i686-pc-linux-gnu) libcurl 7.9.8 (OpenSSL 0.9.6b) (ipv6 enabled)"}
        searchresults = requests.get(searchurl, headers=header)
        soup = BeautifulSoup(searchresults.text, 'html.parser')
        page = re.findall('"track_share_url":"(http[s?]://www\.musixmatch\.com/lyrics/.+?)","', soup.text)
        url = page[0]
        lyricspage = requests.get(url, headers=header)
        soup = BeautifulSoup(lyricspage.text, 'html.parser')
        lyrics = soup.text.split('"body":"')[1].split('","language"')[0]
        lyrics = lyrics.replace("\\n", "\n")
        lyrics = lyrics.replace("\\", "")
    except Exception:
        return None
    return lyrics + url


def wikia(artist, song):
    lyrics = minilyrics.LyricWikia(artist, song)
    url = "http://lyrics.wikia.com/%s:%s" % (artist.replace(' ', '_'), song.replace(' ', '_'))
    if lyrics != 'error':
        return lyrics + url
    else:
        return None


def amalgama_lyrics(artist, song):
    url = amalgama.get_url(artist, song)
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        client.captureMessage(f'{artist} - {song} not found in amalgama {url}')
        return None
    lyrics = amalgama.get_first_translate_text(response.text)
    return f'{lyrics} {url}'


def send_lyrics(message, artist, song):
    lyrics_text = wikia(artist, song)
    if lyrics_text is None:
        handle_request(message.from_user)
        client.captureMessage(f"Lyrics {artist} - {song} not found in wikia")
        lyrics_text = musixmatch(artist, song)
    if lyrics_text is None:
        bot.send_message(message.chat.id, 'Could not find lyrics')
        handle_request(message.from_user)
        client.captureMessage(f"Lyrics {artist} - {song} not found in musixmatch")
        return None

    if lyrics_text:
        bot.send_message(message.chat.id, lyrics_text)
        lyrics_translate = amalgama_lyrics(artist, song)
        if lyrics_translate is None:
            bot.send_message(message.chat.id, 'Translate lyrics not found')
        else:
            try:
                bot.send_message(message.chat.id, lyrics_translate)
            except telebot.apihelper.ApiException as e:
                bot.send_message(message.chat.id, 'Translate is too long ')
                client.captureMessage(f"Translate {artist} - {song} is too long {e}")


def check_chinese(artist):
    return bool(re.findall('[\u4e00-\u9fff]+', artist))


@bot.message_handler(content_types=['text'])
def handle_text(message):
    data = event('voice', 'send_text')
    report(ANALYTICS_TRACKING_ID, ANALYTICS_ACCOUNT_ID, data)

    first_word = message.text.split(' ', 1)[0]
    if first_word.lower() == 'lyrics':
        artist = ""
        song = ""
        songname = message.text.split(first_word + ' ', 1)[1]
        if songname.count(" - ") == 1:
            artist, song = songname.rsplit(" - ", 1)
        if songname.count(" – ") == 1:
            artist, song = songname.rsplit(" – ", 1)
        if songname.count(" - ") == 2:
            artist, song, garbage = songname.rsplit(" - ", 2)
        if " / " in song:
            song, garbage = song.rsplit(" / ", 1)
        song = re.sub(' \(.*?\)', '', song, flags=re.DOTALL)

        if check_chinese(artist):
            bot.send_message(message.chat.id, 'Only English or Russian')
        else:
            send_lyrics(message, artist, song)
    else:
        bot.send_message(message.chat.id, "Just send me voice message and i'll try to recognize the song!")


@bot.message_handler(content_types=['voice'])
def voice_processing(message):
    data = event('voice', 'send_voice')
    report(ANALYTICS_TRACKING_ID, ANALYTICS_ACCOUNT_ID, data)

    duration = message.voice.duration
    if duration < 5:
        bot.send_message(message.chat.id, 'The voice message is too short.')
    elif duration > 30:
        bot.send_message(message.chat.id, 'The voice message is too long.')
    else:
        file_info = bot.get_file(message.voice.file_id)
        file = bot.download_file(file_info.file_path)
        my_file_path = f"bot/{file_info.file_path}"

        with open(my_file_path, 'wb') as f:
            f.write(file)

        data = acr.identify(my_file_path)

        if data['status']['code'] == 0:
            filename_w_ext = os.path.basename(file_info.file_path)
            json_filename, file_extension = os.path.splitext(filename_w_ext)
            with open(f'bot/json/{json_filename}.json', 'w', encoding='utf8') as outfile:
                json.dump(data, outfile, indent=4, sort_keys=True)

            artist = data['metadata']['music'][0]['artists'][0]['name']
            song = data['metadata']['music'][0]['title']

            if check_chinese(artist):
                bot.send_message(message.chat.id, 'Only English or Russian')
            else:
                if song.count(" - ") == 1:
                        song, garbage = song.rsplit(" - ", 1)
                song = re.sub("[(\[].*?[)\]]", "", song).strip()
                about = f"{artist} - {song}"
                bot.send_message(message.chat.id, about)

                genres = get_genres(data)
                if genres != 'Classical':
                    send_lyrics(message, artist, song)
                    yid = media(data, 'youtube')
                    if yid is not None:
                        y_link = 'https://www.youtube.com/watch?v=' + yid
                        bot.send_message(message.chat.id, y_link)
                    else:
                        y_link = get_youtube(artist, song)
                        if y_link is not None:
                            bot.send_message(message.chat.id, y_link)
                else:
                    bot.send_message(message.chat.id, 'this is classical melody')

                sid = media(data, 'spotify')
                if sid is not None:
                    s_link = f'https://open.spotify.com/track/{sid}'
                    bot.send_message(message.chat.id, s_link)
                else:
                    client.captureMessage(f"{artist} - {song} not found in spotify")

                did = media(data, 'deezer')
                if did is not None:
                    d_link = f'http://www.deezer.com/track/{str(did)}'
                    r = requests.get(d_link)
                    if r.status_code != 404:
                        bot.send_message(message.chat.id, d_link)
                else:
                    client.captureMessage(f"{artist} - {song} not found in deezer")
        else:
            snf = 'songs not found'
            bot.send_message(message.chat.id, snf)


if __name__ == '__main__':
    bot.infinity_polling(True)
