import os
from os.path import join, dirname
import re

from dotenv import load_dotenv
import requests
import telebot
from bs4 import BeautifulSoup
from raven import Client

import json
import lyrics as minilyrics
from acr_identify import fetch_metadata

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

client = Client(os.environ.get('SENTRY'))

bot = telebot.TeleBot(os.environ.get('TELEGRAM_TOKEN_TEST'))
error = 'Could not find lyrics.'


def reg(s):
    s = re.sub(r"[^\w\s]$", '', s)
    s = s.replace('$', 's')
    s = s.replace('&', 'and')
    s = s.replace("'", '_')
    s = re.sub(r"[-./\s\W]", '_', s)
    s = s.replace("__", '_')
    return s


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
        client.captureMessage(f"Lyrics {artist} - {song} not found in musixmatch")
        return error
    return lyrics + url


def wikia(artist, song):
    lyrics = minilyrics.LyricWikia(artist, song)
    url = "http://lyrics.wikia.com/%s:%s" % (artist.replace(' ', '_'), song.replace(' ', '_'))
    if lyrics != 'error':
        return lyrics + url
    else:
        client.captureMessage(f"Lyrics {artist} - {song} not found in wikia")
        lyrics = musixmatch(artist, song)
        return lyrics


def amalgama_lyrics(artist, song):
    artist, song = artist.lower(), song.lower()
    if 'the' in artist:
        artist = artist[4:]
    cn = artist[0]
    link = f"http://www.amalgama-lab.com/songs/{cn}/{reg(artist)}/{reg(song)}.html"
    r = requests.get(link)
    if r.status_code != 404:
        soup = BeautifulSoup(r.text, "html.parser")
        s = ''
        for strong_tag in soup.find_all("div", class_="translate"):
            if '\n' in strong_tag.text:
                s = s + strong_tag.text
            else:
                s = s + strong_tag.text + '\n'
        return s + link
    else:
        client.captureMessage(f"translate {artist} - {song} not found in amalgama {link}")


def send_lyrics(message, artist, song):
    lyrics_text = wikia(artist, song)
    try:
        bot.send_message(message.chat.id, lyrics_text)
    except Exception:
        bot.send_message(message.chat.id, 'Lyrics is too long')
        client.captureMessage(f"Lyrics {artist} - {song} is too long")

    if lyrics_text != error:
        lyrics_translate = amalgama_lyrics(artist, song)
        try:
            if lyrics_translate is not None:
                bot.send_message(message.chat.id, lyrics_translate)
            else:
                bot.send_message(message.chat.id, 'Translate lyrics not found')
        except Exception:
            bot.send_message(message.chat.id, 'Translate lyrics is too long')
            client.captureMessage(f"Translate lyrics {artist} - {song} is too long")


def check_chinese(artist):
    return bool(re.findall('[\u4e00-\u9fff]+', artist))


@bot.message_handler(content_types=['text'])
def handle_text(message):
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
    duration = message.voice.duration
    if duration < 5:
        bot.send_message(message.chat.id, 'The voice message is too short.')
    elif duration > 30:
        bot.send_message(message.chat.id, 'The voice message is too long.')
    else:
        file_info = bot.get_file(message.voice.file_id)
        file = bot.download_file(file_info.file_path)

        with open(file_info.file_path, 'wb') as f:
            f.write(file)

        data = fetch_metadata(file_info.file_path)

        if data['status']['code'] == 0:
            name_json = file_info.file_path.split('/')[1].split('.')[0]
            with open(f'json/{name_json}.json', 'w', encoding='utf8') as outfile:
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
    bot.polling(none_stop=True)
