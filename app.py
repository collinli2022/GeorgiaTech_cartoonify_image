from flask import Flask, render_template, flash, request, redirect, url_for
from PIL import Image
import base64
import io

import os
from werkzeug.utils import secure_filename

import cv2
import numpy as np

# input a image path and it will output a cartoonified image
def better_cartoonify(numpy_arr_image, numDownSamples = 2, numBilateralFilters = 15, resize_shape=(1920,1080)):
    ## Get image ##
    orig = np.array(numpy_arr_image) 
    #orig = cv2.cvtColor(orig, cv2.COLOR_BGR2RGB)
    images = {}

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
    return im

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)


## Reference: https://flask.palletsprojects.com/en/1.1.x/patterns/fileuploads/ ##
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        # if user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            print(type(file))
            inputed_image = Image.open(file)
            adjusted_image = better_cartoonify(inputed_image.convert('RGB'))
            data = io.BytesIO()
            inputed_image.save(data, "JPEG")
            encoded_img_data = base64.b64encode(data.getvalue())
            # file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return render_template("index.html", img_data=encoded_img_data.decode('utf-8'))

    # Full Script.
    im = Image.open("test.jpg")
    data = io.BytesIO()
    im.save(data, "JPEG")
    encoded_img_data = base64.b64encode(data.getvalue())
    return render_template("index.html", img_data=encoded_img_data.decode('utf-8'))

@app.route('/')
def hello_world():

    # Full Script.
    im = Image.open("test.jpg")
    data = io.BytesIO()
    im.save(data, "JPEG")
    encoded_img_data = base64.b64encode(data.getvalue())

    return render_template("index.html", img_data=encoded_img_data.decode('utf-8'))

if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)
    sys.stdout.flush()