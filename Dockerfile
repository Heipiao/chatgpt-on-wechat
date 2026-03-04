FROM ghcr.io/zhayujie/chatgpt-on-wechat:latest

# 清空基础镜像 /app 中的所有文件（含隐藏文件如 .git）
RUN rm -rf /app/* /app/.[!.]* /app/..?*
COPY . /app
RUN chmod -R a+rw /app

COPY --chmod=755 docker/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
