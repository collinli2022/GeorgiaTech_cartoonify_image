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

from flask import Flask, render_template, request
from werkzeug.utils import secure_filename

'''
TODO:

- better comments
- make sure vars are specificly label (like path and message)
- reduce blur
- don't hard code paths or anything


- dilation
- erosion 
- consistant black lines (to just the outline [edge detection])
- opencv opening kernel 

'''

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

#app.py
from flask import Flask, flash, request, redirect, url_for, render_template
import urllib.request
import os
from werkzeug.utils import secure_filename
 
app = Flask(__name__)
 
UPLOAD_FOLDER = 'static/uploads/'
 
app.secret_key = "secret key"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
 
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif'])
 
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
     
 
@app.route('/')
def home():
    return render_template('upload.html')
    
@app.route('/', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        flash('No image selected for uploading')
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        better_cartoonify(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        #print('upload_image filename: ' + filename)
        flash('Image successfully uploaded and displayed below')
        return render_template('upload.html', filename=filename)
    else:
        flash('Allowed image types are - png, jpg, jpeg, gif')
        return redirect(request.url)
 
@app.route('/display/<filename>')
def display_image(filename):
    #print('display_image filename: ' + filename)
    return redirect(url_for('static', filename='uploads/' + filename), code=301)
 
if __name__ == "__main__":
    app.run(debug = True)