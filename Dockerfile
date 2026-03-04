FROM ghcr.io/zhayujie/chatgpt-on-wechat:latest

# 清空基础镜像 /app 中的所有文件（含隐藏文件如 .git）
RUN rm -rf /app/* /app/.[!.]* /app/..?*
COPY --chmod=0777 . /app

RUN pip install oss2

COPY --chmod=755 docker/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
