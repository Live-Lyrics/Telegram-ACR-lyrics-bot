import re
from bs4 import BeautifulSoup
import json
import lyrics as minilyrics
import requests
import telebot
from acrcloud.recognizer import ACRCloudRecognizer

token = "Your token from Telegram"
bot = telebot.TeleBot(token)

# ACR cloud
config = {
    # Replace "xxxx xxxx" below with your project's host, access_key and access_secret.
    'host': 'XXXXXXXX',
    'access_key': 'XXXXXXXX',
    'access_secret': 'XXXXXXXX',
    'timeout': 5  # seconds
}
error = 'Could not find lyrics.'


def media(data, keys):
    for i in data['metadata']['music']:
        for key, value in i['external_metadata'].items():
            if keys == 'youtube' == key:
                yid = value['vid']
                return yid
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
        lyrics = error
        print(f"{artist} - {song} not found in musixmatch")
    return lyrics


def wikia(artist, song):
    lyrics = minilyrics.LyricWikia(artist, song)
    if lyrics == 'error':
        musixmatch(artist, song)
        print(f"{artist} - {song} not found in wikia")
    return lyrics


@bot.message_handler(content_types=['voice'])
def voice_processing(message):
    file_info = bot.get_file(message.voice.file_id)
    file = requests.get(f'https://api.telegram.org/file/bot{token}/{file_info.file_path}')
    if file.status_code == 200:
        with open(file_info.file_path, 'wb') as f:
            for chunk in file:
                f.write(chunk)

    recogn = ACRCloudRecognizer(config)
    metadata = recogn.recognize_by_file(file_info.file_path, 0)
    data = json.loads(metadata)

    if data['status']['code'] == 0:
        name_json = file_info.file_path.split('/')[1].split('.')[0]
        with open(f'json/{name_json}.json', 'w', encoding='utf8') as outfile:
            json.dump(data, outfile, indent=4, sort_keys=True)

        artist = data['metadata']['music'][0]['artists'][0]['name']
        song = data['metadata']['music'][0]['title']
        about = f"{artist} - {song}"
        bot.send_message(message.chat.id, about)

        lyrics_user = wikia(artist, song)
        bot.send_message(message.chat.id, lyrics_user)

        yid = media(data, 'youtube')
        if yid is not None:
            y_link = 'https://www.youtube.com/watch?v=' + yid
            bot.send_message(message.chat.id, y_link)
        else:
            print(f"{artist} - {song} not found in youtube")
        sid = media(data, 'spotify')
        if sid is not None:
            s_link = 'https://open.spotify.com/track/' + sid
            bot.send_message(message.chat.id, s_link)
        else:
            print(f"{artist} - {song} not found in spotify")
    else:
        bot.send_message(message.chat.id, 'songs not found')
        print(data)


if __name__ == '__main__':
    bot.polling(none_stop=True)
