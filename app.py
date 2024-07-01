from src.website import create_app
import os, sys

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)


# from flask import Flask, send_from_directory
# import os
#
# from src.website import create_app
# import sys
#
# sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
# app = create_app()
#
# # favicon.ico 파일이 있는 디렉터리의 경로 설정
# # 여기서는 프로젝트 루트의 static 폴더에 favicon.ico 파일을 위치시킨 경우입니다.
# favicon_path = os.path.join(app.root_path, 'static')
#
# # /favicon.ico 경로에 대해 해당 파일을 제공합니다.
# @app.route('/favicon.ico')
# def favicon():
#     return send_from_directory(favicon_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon')
#
# if __name__ == '__main__':
#     app.run()