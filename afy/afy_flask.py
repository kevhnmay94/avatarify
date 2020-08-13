#! /home/easysoft/anaconda3/envs/avatarify/bin/python

import flask
from flask import Flask, request
from subprocess import Popen, PIPE
from afy.arguments import opt
if not flask.current_app:
    app = Flask(__name__)
    app.port_start = 10500
    app.user_max = 6
    app.verbose = True
    app.processes = {}
    app.unused_port = [app.port_start + 2 * i for i in range(app.user_max)]
    app.base_address = "tcp://localhost"
    app.verbose = True
    app.opt = opt
else:
    from flask import current_app as app
from afy import predictor_remote
import base64
import numpy as np
import shlex
import cv2
import time
import binascii, os
from afy.utils import crop, resize
from afy import afy_flask_register_status, afy_flask_avatar_status, afy_flask_predict_status, afy_flask_logout_status

Popen(shlex.split("kill -9 $(ps aux | grep 'afy/cam_fomm.py' | awk '{print $2}') 2> /dev/null"))
time.sleep(2)

def vprint(*data):
    if app.verbose:
        print(*data)

def generate_token():
    return binascii.hexlify(os.urandom(20)).decode()

def register_response(status=afy_flask_register_status.UNKNOWN_ERROR,token=None, error=None):
    resp = {}
    resp['status'] = status
    if token is not None:
        resp['token'] = token
    if error is not None:
        resp['error'] = error
    return resp

def avatar_response(status=afy_flask_avatar_status.UNKNOWN_ERROR,error=None):
    resp = {}
    resp['status'] = status
    if error is not None:
        resp['error'] = error
    return resp

def predict_response(status=afy_flask_avatar_status.UNKNOWN_ERROR,image=None, error=None):
    resp = {}
    resp['status'] = status
    if image is not None:
        resp['image'] = image
    if error is not None:
        resp['error'] = error
    return resp


@app.route('/avatarify', methods=['GET'])
def register():
    try:
        if app.unused_port:
            port = app.unused_port.pop()
        else:
            return register_response(status=afy_flask_register_status.QUOTA_EXCEEDED,error="Quota Exceeded")
        in_addr = app.base_address + ":" + str(port)
        out_addr = app.base_address + ":" + str(port+1)
        sps = shlex.split(f'./run.sh --is-worker --in-port {port} --out-port {port+1} --no-vcam')
        ps = Popen(sps)
        time.sleep(2)
        try:
            predictor = predictor_remote.PredictorRemote(in_addr=in_addr,out_addr=out_addr, **app.opt)
        except ConnectionError as err:
            return register_response(status=afy_flask_register_status.CONNECTION_ERROR,error=err)
        while True:
            token = generate_token()
            if token not in app.processes:
                break
        app.processes[token]['port'] = port
        app.processes[token]['ps'] = ps
        app.processes[token]['predictor'] = predictor
        return register_response(status=afy_flask_register_status.SUCCESS,token=token)
    except Exception as e:
        return register_response(error=e)


@app.route('/avatarify/<token>/change_avatar', methods=['POST'])
def change_avatar(token):
    try:
        ava_f = request.files['avatar']
        if ava_f is not None:
            ava_g = ava_f.read()
            ava_np = np.fromstring(ava_g, np.uint8)
            ava_h = cv2.imdecode(ava_np,cv2.IMREAD_COLOR)
            if token in app.processes:
                d = app.processes[token]['predictor']
                d['predictor'].set_source_image(ava_h)
                d['predictor'].reset_frames()
                return avatar_response(status=afy_flask_avatar_status.SUCCESS)
            return avatar_response(status=afy_flask_avatar_status.NO_PREDICTOR,error="Predictor not available")
        return avatar_response(status=afy_flask_avatar_status.INPUT_IMAGE_ERROR,error="Invalid image / image corrupted")
    except Exception as e:
        return avatar_response(error=e)

@app.route('/avatarify/<token>/predict', methods=['POST'])
def predict(token):
    try:
        IMG_SIZE = 256
        frame_proportion = 0.9
        frame_offset_x = 0
        frame_offset_y = 0
        img = request.files['image']
        if img is not None:
            img_g = img.read()
            img_np = np.fromstring(img_g, np.uint8)
            frame = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
            if token in app.processes:
                d = app.processes[token]['predictor']
                frame = frame[..., ::-1]
                frame_orig = frame.copy()
                frame, lrudwh = crop(frame, p=frame_proportion, offset_x=frame_offset_x, offset_y=frame_offset_y)
                frame_lrudwh = lrudwh
                frame = resize(frame, (IMG_SIZE, IMG_SIZE))[..., :3]
                out = d['predictor'].predict(frame)
                if out is not None:
                    out = cv2.cvtColor(out,cv2.COLOR_BGR2RGB)
                    out = cv2.imencode(cv2.IMWRITE_JPEG_QUALITY,out)
                    out = base64.b64encode(out).decode("utf-8")
                    return predict_response(status=afy_flask_predict_status.SUCCESS,image=out)
                return predict_response(status=afy_flask_predict_status.SUCCESS)
            return avatar_response(status=afy_flask_predict_status.NO_PREDICTOR, error="Predictor not available")
        return avatar_response(status=afy_flask_predict_status.INPUT_IMAGE_ERROR, error="Invalid image / image corrupted")
    except Exception as e:
        return avatar_response(error=e)


@app.route('/avatarify/<token>/logout', methods=['GET'])
def logout(token):
    if token in app.processes:
        d = app.processes.pop(token)
        port = d['port']
        ps = d['ps']
        predictor = d['predictor']
        predictor.stop()
        ps.kill()
        app.unused_port.append(port)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8093, debug=app.verbose)