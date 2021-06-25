from flask import Flask, render_template, flash, request, redirect, url_for
from PIL import Image
import base64
import io

import os
from werkzeug.utils import secure_filename

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