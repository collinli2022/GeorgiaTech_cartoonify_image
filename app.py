"""An example flask application demonstrating server-sent events."""

from hashlib import sha1
from shutil import rmtree
from stat import S_ISREG, ST_CTIME, ST_MODE
import json
import os
import time

from PIL import Image, ImageFile
from gevent.event import AsyncResult
from gevent.queue import Empty, Queue
from gevent.timeout import Timeout
import flask

import cv2 # for image processing
import numpy as np # to store image
import matplotlib.pyplot as plt
import sys
import requests

# input a image path and it will output a cartoonified image
def better_cartoonify(image_path, numDownSamples = 2, numBilateralFilters = 15, resize_shape=(1920,1080)):
    ## Get image ##
    orig = cv2.imread(image_path) 
    orig = cv2.cvtColor(orig, cv2.COLOR_BGR2RGB)
    images = {}
    if orig is None:
        print("Path incorrect, no image found")
        sys.exit()

    ## Original ##
    ## Resize to resize_shape ##
    images['orig1'] = cv2.resize(orig, resize_shape)

    ## Placeholder ##
    images['placeholder'] = images['orig1'].copy()

    ## downsample image using Gaussian pyramid ##
    for _ in range(numDownSamples): 
      orig = cv2.pyrDown(orig)
    images['downsample'] = cv2.resize(orig, resize_shape)

    ## repeatedly apply small bilateral filter instead of applying ##
    ## one large filter ##
    for _ in range(numBilateralFilters): 
      orig = cv2.bilateralFilter(orig, 2, 2, 2) # arguments of diameter of each pixel neighborhood, sigmaColor, sigmaColor (https://www.geeksforgeeks.org/python-bilateral-filtering/)
    images['bilateral'] = cv2.resize(orig, resize_shape)

    # upsample image to original size 
    for _ in range(numDownSamples): 
      orig = cv2.pyrUp(orig)
    images['upsample'] = cv2.resize(orig, resize_shape)

    ## MedianBlur for even more blur ##
    # orig = cv2.medianBlur(orig, 3)
    images['blur'] = cv2.resize(orig, resize_shape)

    ## Grayscale (to improve smoothing) ##
    grayScaleImage = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
    images['grayscale'] = cv2.resize(grayScaleImage, resize_shape)

    ## Adaptive Edge Threshold ## # TODO: thinner edges and greater threshold 
    getEdge = cv2.adaptiveThreshold(grayScaleImage, 255, 
                                    cv2.ADAPTIVE_THRESH_MEAN_C, 
                                    cv2.THRESH_BINARY, 9, 2) # TODO: increase threshold
    images['edge'] = cv2.resize(getEdge, resize_shape)

    ## Color Filter ##
    colorImage = cv2.bilateralFilter(orig, 9, 300, 300) # filter color
    images['color filter'] = cv2.resize(colorImage, resize_shape)

    ## Combined ##
    cartoonImage = cv2.bitwise_and(colorImage, colorImage, mask=getEdge) # combind image and edges
    images['combined'] = cv2.resize(cartoonImage, resize_shape)

    im = Image.fromarray(cartoonImage)
    new_path = image_path.replace('.jpg', '_cartoon.jpg')
    im.save(new_path)
    return new_path

## Code taken from https://github.com/bboe/flask-image-uploader ##
    
## Constants ##
DATA_DIR = 'tmp'
KEEP_ALIVE_DELAY = 25
MAX_IMAGE_SIZE = 1600, 1200
MAX_IMAGES = 10
MAX_DURATION = 300

app = flask.Flask(__name__, static_folder=DATA_DIR)
BROADCAST_QUEUE = Queue()


try:  # Reset saved files on each start
    rmtree(DATA_DIR, True)
    os.mkdir(DATA_DIR)
except OSError:
    pass


def broadcast(message):
    """Notify all waiting waiting gthreads of message."""
    waiting = []
    try:
        while True:
            waiting.append(BROADCAST_QUEUE.get(block=False))
    except Empty:
        pass
    print('Broadcasting {} messages'.format(len(waiting)))
    for item in waiting:
        item.set(message)


def receive():
    """Generator that yields a message at least every KEEP_ALIVE_DELAY seconds.
    yields messages sent by `broadcast`.
    """
    now = time.time()
    end = now + MAX_DURATION
    tmp = None
    # Heroku doesn't notify when clients disconnect so we have to impose a
    # maximum connection duration.
    while now < end:
        if not tmp:
            tmp = AsyncResult()
            BROADCAST_QUEUE.put(tmp)
        try:
            yield tmp.get(timeout=KEEP_ALIVE_DELAY)
            tmp = None
        except Timeout:
            yield ''
        now = time.time()


def safe_addr(ip_addr):
    """Strip off the trailing two octets of the IP address."""
    return '.'.join(ip_addr.split('.')[:2] + ['xxx', 'xxx'])


def save_normalized_image(path, data):
    """Generate an RGB thumbnail of the provided image."""
    image_parser = ImageFile.Parser()
    try:
        image_parser.feed(data)
        image = image_parser.close()
    except IOError:
        return False, False
    image.thumbnail(MAX_IMAGE_SIZE, Image.ANTIALIAS)
    if image.mode != 'RGB':
        image = image.convert('RGB')

    ## Save image and save cartoonified image ##
    image.save(path)
    cartoonified_image_path = better_cartoonify(path)
    return True, cartoonified_image_path


def event_stream(client):
    """Yield messages as they come in."""
    force_disconnect = False
    try:
        for message in receive():
            yield 'data: {}\n\n'.format(message)
        print('{} force closing stream'.format(client))
        force_disconnect = True
    finally:
        if not force_disconnect:
            print('{} disconnected from stream'.format(client))


@app.route('/post', methods=['POST'])
def post():
    """Handle image uploads."""
    sha1sum = sha1(flask.request.data).hexdigest()
    target = os.path.join(DATA_DIR, '{}.jpg'.format(sha1sum))
    message = json.dumps({'src': target,
                          'ip_addr': safe_addr(flask.request.access_route[0])})
    try:
        ## making program more robust by not hard coding anything ##
        saving_success, cartoonified_image_path = save_normalized_image(target, flask.request.data)
        if saving_success:
            message = json.dumps({'src': cartoonified_image_path, 'ip_addr': safe_addr(flask.request.access_route[0])})
            broadcast(message)  # Notify subscribers of completion
    except Exception as exception:  # Output errors
        return '{}'.format(exception)
    return 'success'


@app.route('/stream')
def stream():
    """Handle long-lived SSE streams."""
    return flask.Response(event_stream(flask.request.access_route[0]),
                          mimetype='text/event-stream')

@app.route('/')
def home():
    """Provide the primary view along with its javascript."""
    # Code adapted from: http://stackoverflow.com/questions/168409/
    image_infos = []
    for filename in os.listdir(DATA_DIR):
        filepath = os.path.join(DATA_DIR, filename)
        file_stat = os.stat(filepath)
        if S_ISREG(file_stat[ST_MODE]):
            image_infos.append((file_stat[ST_CTIME], filepath))

    images = []
    for i, (_, path) in enumerate(sorted(image_infos, reverse=True)):
        if i >= MAX_IMAGES:
            os.unlink(path)
            continue
        images.append('<div><img alt="User uploaded image" src="{}" /></div>'
                      .format(path))
    return """

<!doctype html>
<title>Image Uploader</title>
<meta charset="utf-8" />
<script src="//ajax.googleapis.com/ajax/libs/jquery/1.9.1/jquery.min.js"></script>
<script src="//ajax.googleapis.com/ajax/libs/jqueryui/1.10.1/jquery-ui.min.js"></script>
<link rel="stylesheet" href="//ajax.googleapis.com/ajax/libs/jqueryui/1.10.1/themes/vader/jquery-ui.css" />
<style>
  body {
    max-width: 800px;
    margin: auto;
    padding: 1em;
    background: black;
    color: #fff;
    font: 16px/1.6 menlo, monospace;
    text-align:center;
  }
  a {
    color: #fff;
  }
  .notice {
    font-size: 80%%;
  }
#drop {
    font-weight: bold;
    text-align: center;
    padding: 1em 0;
    margin: 1em 0;
    color: #555;
    border: 2px dashed #555;
    border-radius: 7px;
    cursor: default;
}
#drop.hover {
    color: #f00;
    border-color: #f00;
    border-style: solid;
    box-shadow: inset 0 3px 4px #888;
}
</style>
<h3>Image Uploader</h3>
<p>Upload an image for everyone to see. Valid images are pushed to everyone
currently connected, and only the most recent %s images are saved.</p>
<p>The complete source for this Flask web service can be found at:
<a href="https://github.com/bboe/flask-image-uploader">https://github.com/bboe/flask-image-uploader</a></p>
<p class="notice">Disclaimer: The author of this application accepts no responsibility for the
images uploaded to this web service. To discourage the submission of obscene images, IP
addresses with the last two octets hidden will be visibly associated with uploaded images.</p>
<noscript>Note: You must have javascript enabled in order to upload and
dynamically view new images.</noscript>
<fieldset>
  <p id="status">Select an image</p>
  <div id="progressbar"></div>
  <input id="file" type="file" />
  <div id="drop">or drop image here</div>
</fieldset>
<h3>Uploaded Images (updated in real-time)</h3>
<div id="images">%s</div>
<script>
  function sse() {
      var source = new EventSource('/stream');
      source.onmessage = function(e) {
          if (e.data == '')
              return;
          var data = $.parseJSON(e.data);
          var upload_message = 'Image uploaded by ' + data['ip_addr'];
          var image = $('<img>', {alt: upload_message, src: data['src']});
          var container = $('<div>').hide();
          container.append($('<div>', {text: upload_message}));
          container.append(image);
          $('#images').prepend(container);
          image.load(function(){
              container.show('blind', {}, 1000);
          });
      };
  }
  function file_select_handler(to_upload) {
      var progressbar = $('#progressbar');
      var status = $('#status');
      var xhr = new XMLHttpRequest();
      xhr.upload.addEventListener('loadstart', function(e1){
          status.text('uploading image');
          progressbar.progressbar({max: e1.total});
      });
      xhr.upload.addEventListener('progress', function(e1){
          if (progressbar.progressbar('option', 'max') == 0)
              progressbar.progressbar('option', 'max', e1.total);
          progressbar.progressbar('value', e1.loaded);
      });
      xhr.onreadystatechange = function(e1) {
          if (this.readyState == 4)  {
              if (this.status == 200)
                  var text = 'upload complete: ' + this.responseText;
              else
                  var text = 'upload failed: code ' + this.status;
              status.html(text + '<br/>Select an image');
              progressbar.progressbar('destroy');
          }
      };
      xhr.open('POST', '/post', true);
      xhr.send(to_upload);
  };
  function handle_hover(e) {
      e.originalEvent.stopPropagation();
      e.originalEvent.preventDefault();
      e.target.className = (e.type == 'dragleave' || e.type == 'drop') ? '' : 'hover';
  }
  $('#drop').bind('drop', function(e) {
      handle_hover(e);
      if (e.originalEvent.dataTransfer.files.length < 1) {
          return;
      }
      file_select_handler(e.originalEvent.dataTransfer.files[0]);
  }).bind('dragenter dragleave dragover', handle_hover);
  $('#file').change(function(e){
      file_select_handler(e.target.files[0]);
      e.target.value = '';
  });
  sse();
  var _gaq = _gaq || [];
  _gaq.push(['_setAccount', 'UA-510348-17']);
  _gaq.push(['_trackPageview']);
  (function() {
    var ga = document.createElement('script'); ga.type = 'text/javascript'; ga.async = true;
    ga.src = ('https:' == document.location.protocol ? 'https://ssl' : 'http://www') + '.google-analytics.com/ga.js';
    var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(ga, s);
  })();
</script>
""" % (MAX_IMAGES, '\n'.join(images))  # noqa


if __name__ == '__main__':
    app.run(host='localhost', debug=True, use_reloader=True)