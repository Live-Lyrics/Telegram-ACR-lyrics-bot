import re
import json

import requests
from bs4 import BeautifulSoup


# function to return lyrics grabbed from lyricwikia
def LyricWikia(artist, title):
    url = 'http://lyrics.wikia.com/api.php?action=lyrics&artist={artist}&song={title}&fmt=json&func=getSong'.format(
        artist=artist,
        title=title).replace(" ", "%20")
    r = requests.get(url)
    # We got some bad formatted JSON data... So we need to fix stuff :/
    returned = r.text
    returned = returned.replace('"', "")
    returned = returned.replace("\'", "\"")
    returned = returned.replace("song = ", "")
    returned = json.loads(returned)
    if returned["lyrics"] != "Not found":
        # set the url to the url we just recieved, and retrieving it
        r = requests.get(returned["url"])
        soup = BeautifulSoup(r.text, 'html.parser')
        soup = soup.find("div", {"class": "lyricbox"})
        [elem.extract() for elem in soup.findAll('div')]
        [elem.replaceWith('\n') for elem in soup.findAll('br')]
        soup = BeautifulSoup(re.sub(r'(<!--[.\s\S]*-->)', '', str(soup)), 'html.parser')
        [elem.extract() for elem in soup.findAll('script')]
        return soup.getText()
    else:
        return None
