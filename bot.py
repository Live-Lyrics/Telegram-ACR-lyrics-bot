import json
import lyrics as minilyrics
import requests
import telebot
from acrcloud.recognizer import ACRCloudRecognizer

token = "You token from Telegram"
bot = telebot.TeleBot(token)

# ACR cloud
config = {
    # Replace "xxxx xxxx" below with your project's host, access_key and access_secret.
    'host': 'XXXXXXXX',
    'access_key': 'XXXXXXXX',
    'access_secret': 'XXXXXXXX',
    'timeout': 5  # seconds
}


def media(data, keys):
    for i in data["metadata"]["music"]:
        for key, value in i['external_metadata'].items():
            if keys == 'youtube' == key:
                yid = value['vid']
                return yid
            if keys == 'spotify' == key:
                sid = value['track']['id']
                return sid


def wikia(artist, song):
    error = "Could not find lyrics."
    lyrics = minilyrics.LyricWikia(artist, song)
    if lyrics == "error":
        lyrics = error
        print('{} - {} not found in wikia'.format(artist, song))
    return lyrics


@bot.message_handler(content_types=['voice'])
def voice_processing(message):
    file_info = bot.get_file(message.voice.file_id)
    file = requests.get('https://api.telegram.org/file/bot{0}/{1}'.format(token, file_info.file_path))
    if file.status_code == 200:
        with open(file_info.file_path, 'wb') as f:
            for chunk in file:
                f.write(chunk)

    recogn = ACRCloudRecognizer(config)
    metadata = recogn.recognize_by_file(file_info.file_path, 0)
    data = json.loads(metadata)
    if data['status']['code'] == 0:
        with open('json/{}.json'.format(file_info.file_path.split('/')[1].split('.')[0]), 'w',
                  encoding='utf8') as outfile:
            json.dump(data, outfile, indent=4, sort_keys=True)

        artist = data["metadata"]["music"][0]["artists"][0]["name"]
        song = data["metadata"]["music"][0]["title"]
        bot.send_message(message.chat.id, '{} - {}'.format(artist, song))

        text = wikia(artist, song)
        bot.send_message(message.chat.id, text)

        yid = media(data, 'youtube')
        if yid is not None:
            bot.send_message(message.chat.id, 'https://www.youtube.com/watch?v=' + media(data, 'youtube'))
        else:
            print('{} - {} not found in youtube'.format(artist, song))

        sid = media(data, 'spotify')
        if sid is not None:
            bot.send_message(message.chat.id, 'https://open.spotify.com/track/' + media(data, 'spotify'))
        else:
            print('{} - {} not found in spotify'.format(artist, song))
    else:
        bot.send_message(message.chat.id, 'songs not found')


if __name__ == '__main__':
    bot.polling(none_stop=True)
