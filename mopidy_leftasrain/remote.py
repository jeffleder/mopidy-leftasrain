from __future__ import unicode_literals
import json
import os
import time
import urllib
import urllib2
import urlparse

from mopidy.models import Track, Album, Artist

from . import logger

COVER_URL = u"http://www.leftasrain.com/img/covers/%s"
SONG_URL = u"http://leftasrain.com/musica/"
NEXT_TRACK_URL = u"http://leftasrain.com/getNextTrack.php?%s"

FIELD_MAPPING = {
    0: u"id",
    1: u"date",
    2: u"track_name",
    3: u"album",
    4: u"url",
    5: u"comment",
    8: u"cover",
    9: u"post",
}


def track_from_song_data(data, remote_url=False):
    if remote_url:
        uri = urlparse.urljoin(SONG_URL, "%s.mp3" % data["url"])
    else:
        uri = "leftasrain:track:%s - %s.%s" % (data["artist"],
                                               data["track_name"],
                                               data["id"])

    return Track(
        name=data["track_name"],
        artists=[Artist(name=data["artist"])],
        album=Album(name="Leftasrain",
                    images=[COVER_URL % data["cover"]]),
        comment=data["comment"],
        date=data["date"],
        track_no=int(data["id"]),
        last_modified=data["last_modified"],
        uri=uri
    )


def split_title(t):
    """Split (artist, title) from "artist - title" """

    artist, title = "", ""
    try:
        values = t.split(" - ")
        artist = values[0]
        if len(values) > 2:
            title = " - ".join(values[1:])
        else:
            title = values[1]
    except IndexError:
        title = t
    finally:
        return artist, title


def map_song_data(data):
    """Map a list of song attributes to a dict with meaningful keys"""

    result = {}
    for i, v in enumerate(data):
        if i not in FIELD_MAPPING:
            continue
        field = FIELD_MAPPING[i]
        if field == "track_name":
            a, t = split_title(v)
            result["artist"] = a
            result["track_name"] = t
        else:
            result[field] = v
    result["last_modified"] = int(time.time())

    return result


class LeftAsRain(object):

    def __init__(self, timeout, db_filename):
        self._timeout = timeout
        self._total = None
        self.db_filename = db_filename
        self._db = {}

    @property
    def ids(self):
        return self._db.keys()

    @property
    def songs(self):
        return self._db.values()

    @property
    def total(self):
        """Returns the total number of songs on leftasrain.com"""

        if not self._total:
            try:
                self._total = int(self._fetch_song(-1, use_cache=False)["id"]) + 1
            except Exception as e:
                logger.exception(str(e))
                self._total = 0

        return self._total

    def save_db(self):

        with open(self.db_filename, "w") as f:
            json.dump(self._db, f, indent=4)

    def load_db(self):

        if os.path.exists(self.db_filename):
            with open(self.db_filename, "r") as f:
                self._db = json.load(f)

    def _fetch_song(self, song_id, use_cache=True):
        """Returns a list of song attributes"""

        if not isinstance(song_id, int):
            song_id = int(song_id)

        if use_cache and str(song_id) in self._db:
            logger.debug("leftasrain: db hit for ID: %d" % song_id)
            return self._db[str(song_id)]

        params = urllib.urlencode({"currTrackEntry": song_id + 1,
                                   "shuffle": "false"})
        url = NEXT_TRACK_URL % params
        try:
            result = urllib2.urlopen(url, timeout=self._timeout)
            data = map_song_data(json.load(result))
            if use_cache:
                self._db[str(song_id)] = data
            return data
        except urllib2.HTTPError as e:
            logger.debug("Fetch failed, HTTP %s: %s", e.code, e.reason)
        except (IOError, ValueError) as e:
            logger.debug("Fetch failed: %s", e)

    def validate_lookup_uri(self, uri):
        if "." not in uri:
            raise ValueError("Wrong leftasrain URI format")
        try:
            id_ = uri.split(".")[-1]
            if not id_.isdigit():
                raise ValueError("leftasrain song ID must be a positive int")
            if int(id_) >= self.total:
                raise ValueError("No such leftasrain song with ID: %s" % id_)
        except Exception as e:
            raise ValueError("Error while validating URI: %s" % str(e))

    def track_from_id(self, id_, remote_url=False):
        s = self._fetch_song(id_)
        return track_from_song_data(s, remote_url)

    def tracks_from_filter(self, f, remote_url=False):
        return map(lambda t: track_from_song_data(t, remote_url),
                   filter(f, self._db.itervalues()))