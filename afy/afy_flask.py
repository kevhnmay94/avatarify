app = None

import flask
from flask import Flask, request
from subprocess import Popen, PIPE
import importlib
afy_spec = importlib.util.find_spec("afy")
afy_found = afy_spec is not None
import base64
import numpy as np
import shlex
import cv2
import time
import binascii, os
if afy_found:
    from afy.arguments import opt
    from afy import predictor_remote
    from afy.utils import crop, resize
    from afy import afy_flask_register_status, afy_flask_avatar_status, afy_flask_predict_status, afy_flask_logout_status
else:
    from arguments import opt
    import predictor_remote
    from utils import crop, resize
    import afy_flask_register_status, afy_flask_avatar_status, afy_flask_predict_status, afy_flask_logout_status
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
if app.verbose:
    import traceback

def vprint(*data):
    if app.verbose:
        print(*data)

def generate_token():
    return str(binascii.hexlify(os.urandom(20)).decode())

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

def logout_response(status=afy_flask_logout_status.UNKNOWN_ERROR,error=None):
    resp = {}
    resp['status'] = status
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
            predictor_args = {
                'config_path': app.opt.config,
                'checkpoint_path': app.opt.checkpoint,
                'relative': app.opt.relative,
                'adapt_movement_scale': app.opt.adapt_scale,
                'enc_downscale': app.opt.enc_downscale
            }
            predictor = predictor_remote.PredictorRemote(in_addr=in_addr,out_addr=out_addr, **predictor_args)
        except ConnectionError as err:
            if app.verbose:
                traceback.print_exc()
            return register_response(status=afy_flask_register_status.CONNECTION_ERROR,error=str(err))
        while True:
            token = generate_token()
            if token not in app.processes:
                break
        app.processes[token] = {}
        app.processes[token]['port'] = port
        app.processes[token]['ps'] = ps
        app.processes[token]['predictor'] = predictor
        return register_response(status=afy_flask_register_status.SUCCESS,token=token)
    except Exception as e:
        if app.verbose:
            traceback.print_exc()
        return register_response(error=str(e))


@app.route('/avatarify/<token>/change_avatar', methods=['POST'])
def change_avatar(token):
    try:
        IMG_SIZE = 256
        ava_f = request.files['avatar']
        if ava_f is not None:
            ava_g = ava_f.read()
            ava_np = np.fromstring(ava_g, np.uint8)
            ava_h = cv2.imdecode(ava_np,cv2.IMREAD_COLOR)
            if token in app.processes:
                predictor = app.processes[token]['predictor']
                if ava_h.ndim == 2:
                    ava_h = np.tile(ava_h[..., None], [1, 1, 3])
                ava_h = ava_h[..., :3][..., ::-1]
                ava_h = resize(ava_h, (IMG_SIZE, IMG_SIZE))
                vprint('set_source_image')
                predictor.set_source_image(ava_h)
                vprint('finished set_source_image')
                vprint('reset_frames')
                predictor.reset_frames()
                vprint('finished reset_frames')
                return avatar_response(status=afy_flask_avatar_status.SUCCESS)
            return avatar_response(status=afy_flask_avatar_status.NO_PREDICTOR,error="Predictor not available")
        return avatar_response(status=afy_flask_avatar_status.INPUT_IMAGE_ERROR,error="Invalid image / image corrupted")
    except Exception as e:
        if app.verbose:
            traceback.print_exc()
        return avatar_response(error=str(e))

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
                predictor = app.processes[token]['predictor']
                frame = frame[..., ::-1]
                frame_orig = frame.copy()
                frame, lrudwh = crop(frame, p=frame_proportion, offset_x=frame_offset_x, offset_y=frame_offset_y)
                frame_lrudwh = lrudwh
                frame = resize(frame, (IMG_SIZE, IMG_SIZE))[..., :3]
                out = predictor.predict(frame)
                if out is not None:
                    out = cv2.cvtColor(out,cv2.COLOR_BGR2RGB)
                    _, out = cv2.imencode('.jpg', out)
                    out = out.tobytes()
                    out = base64.b64encode(out).decode("utf-8")
                    return predict_response(status=afy_flask_predict_status.SUCCESS,image=out)
                return predict_response(status=afy_flask_predict_status.SUCCESS)
            return predict_response(status=afy_flask_predict_status.NO_PREDICTOR, error="Predictor not available")
        return predict_response(status=afy_flask_predict_status.INPUT_IMAGE_ERROR, error="Invalid image / image corrupted")
    except Exception as e:
        if app.verbose:
            traceback.print_exc()
        return predict_response(error=str(e))


@app.route('/avatarify/<token>/logout', methods=['GET'])
def logout(token):
    try:
        if token in app.processes:
            d = app.processes.pop(token)
            port = d['port']
            ps = d['ps']
            predictor = d['predictor']
            predictor.stop()
            ps.kill()
            app.unused_port.append(port)
        return logout_response(afy_flask_logout_status.SUCCESS)
    except Exception as e:
        if app.verbose:
            traceback.print_exc()
        return logout_response(error=str(e))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8093, debug=app.verbose)