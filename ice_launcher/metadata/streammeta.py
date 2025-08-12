#!/usr/bin/env python3
import sys, urllib.request, urllib.error, urllib.parse

TIMEOUT = 60.0
MAX_RETRY = 64
DEBUG = False

def _open_stream(url, cookiejar=None):
  request = urllib.request.Request(url)
  request.add_header('Icy-MetaData', "1")
  request.add_header("User-Agent", "Lavf/58.26.101") # MPC-HC, Some streams send advertising...
  handlers = [ urllib.request.HTTPCookieProcessor(cookiejar) ] if cookiejar is not None else []
  opener   = urllib.request.build_opener(*handlers)
  return opener.open(request, timeout=TIMEOUT)

class MetaError(RuntimeError): pass

def get_meta(url, skip_meta=None, cookiejar=None):
  response = _open_stream(url, cookiejar=cookiejar) 
  meta = None

  try:
    icy_metaint_header = response.headers.get('icy-metaint')
    if icy_metaint_header is not None and int(icy_metaint_header) != 0:
      metaint = int(icy_metaint_header)
      retry   = MAX_RETRY
      while retry > 0:
        read_buffer = metaint # +255
        content = response.read(read_buffer)
        clen = response.read(1) if content else None
        if clen:
          clen = clen[0] * 16
          content = response.read(clen)
          if content:
            if DEBUG: print("Received %d bytes" % len(content), file=sys.stderr)
            content = content.replace(b'\0', b'')
            if DEBUG: print("Content: {0}".format(repr(content)), file=sys.stderr)
            meta = [ v.split(b"=", 1) for v in content.split(b";") if v and v.strip(b"'") and b"=" in v ] # recently, MUC returns "...;';"
            try:
               meta = [ (k.decode("utf-8"), v.decode("utf-8").strip("'")) for k, v in meta ]
               meta = dict(meta)
            except Exception as exc: # pragma: no cover
              print("Error '{0}'. meta = {1}".format(exc, meta))
              raise
            if not skip_meta: break
            key, val = skip_meta
            if DEBUG: print("Skip %s: %s" % (repr(skip_meta), meta.get(key)), file=sys.stderr)
            if meta.get(key) is None or val.match(meta[key]) is None: break
        if DEBUG: print("Retrying... (clen=%s)" % clen, file=sys.stderr) # pragma: no cover
        retry -= 1

      if  retry <= 0:
        raise MetaError("Read retry limit exceeded")
    else:
      meta = None
  finally:
    response.close()
  return meta
  
def test(): # pragma: no cover # just a scratchpad for command line tests...
  URL = "http://br_mp3-bayern3_s.akacast.akamaistream.net/7/464/142692/v1/gnl.akacast.akamaistream.net/br_mp3_bayern3_s"
  URL = "http://br-br3-live.cast.addradio.de/br/br3/live/mp3/56/stream.mp3"
  URL = "http://br-br1-obb.cast.addradio.de/br/br1/obb/mp3/56/stream.mp3"
  URL = "http://mp3channels.webradio.rockantenne.de/munich-city-nights"

  skip = None
  skip = ('adw_ad', 'true')

  import os, http.cookiejar
  cookies = http.cookiejar.MozillaCookieJar("streammeta.cookies")
  if os.path.isfile("streammeta.cookies"): cookies.load()

  for i in range(5):
    print(cookies)
    meta = get_meta(URL, skip_meta=skip, cookiejar=cookies)
    if not meta: print("EMPTY"); continue
    import pprint
    pprint.pprint(meta)
    for k in meta:
      print(k, meta[k])

  cookies.save()

if __name__ == "__main__": # pragma: no cover
  test()
  
