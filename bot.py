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


def reg(s):
    s = re.sub(r"[^\w\s]$", '', s)
    s = s.replace('$', 's')
    s = re.sub(r"[-./\s\W]", '_', s).lower()
    return s


def amalgama_lyrics(artist, song):
    cn = artist[0].lower()
    link = f"http://www.amalgama-lab.com/songs/{cn}/{reg(artist)}/{reg(song)}.html"
    r = requests.get(link)
    if r.status_code != 404:
        soup = BeautifulSoup(r.text, "html.parser")  # make soup that is parse-able by bs
        s = ''
        for strong_tag in soup.find_all("div", class_="translate"):
            if '\n' in strong_tag.text:
                s = s + strong_tag.text
            else:
                s = s + strong_tag.text + '\n'
        return s + link
    else:
        print(f"translate {artist} - {song} not found")


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
        print(f"{artist} - {song} found in musixmatch")
    except Exception:
        lyrics = error
        print(f"{artist} - {song} not found in musixmatch")
    return lyrics + url


def wikia(artist, song):
    lyrics = minilyrics.LyricWikia(artist, song)
    url = "http://lyrics.wikia.com/%s:%s" % (artist.replace(' ', '_'), song.replace(' ', '_'))
    if lyrics == 'error':
        print(f"{artist} - {song} not found in wikia")
        lyrics = musixmatch(artist, song)
    return lyrics + url


def send_lyrics(message, artist, song):
    lyrics_text = wikia(artist, song)
    try:
        bot.send_message(message.chat.id, lyrics_text)
        lyrics_translate = amalgama_lyrics(artist, song)
        if lyrics_translate is not None:
            bot.send_message(message.chat.id, lyrics_translate)
        else:
            bot.send_message(message.chat.id, 'Translate not found')
    except Exception:
        bot.send_message(message.chat.id, 'Song text is too long')


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
        send_lyrics(message, artist, song)
    else:
        bot.send_message(message.chat.id, "Just send me voice message and i'll try to recognize the song!")


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
        if song.count(" - ") == 1:
                song, garbage = song.rsplit(" - ", 1)
        song = re.sub("[(\[].*?[)\]]", "", song)
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
                bot.send_message(message.chat.id, y_link)
        else:
            bot.send_message(message.chat.id, 'this is classical melody')

        sid = media(data, 'spotify')
        if sid is not None:
            s_link = f'https://open.spotify.com/track/{sid}'
            bot.send_message(message.chat.id, s_link)
        else:
            print(f"{artist} - {song} not found in spotify")

        did = media(data, 'deezer')
        if did is not None:
            d_link = f'http://www.deezer.com/track/{str(did)}'
            bot.send_message(message.chat.id, d_link)
        else:
            print(f"{artist} - {song} not found in deezer")
    else:
        bot.send_message(message.chat.id, 'songs not found')


if __name__ == '__main__':
    bot.polling(none_stop=True)
