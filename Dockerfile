FROM ghcr.io/zhayujie/chatgpt-on-wechat:latest

# 清空基础镜像 /app 中的所有文件（含隐藏文件如 .git）
RUN rm -rf /app/* /app/.[!.]* /app/..?*
COPY --chmod=0777 . /app

# 用 root 安装依赖
USER root
RUN pip install --no-cache-dir oss2 PyMySQL

# 再切回普通用户
USER noroot

COPY --chmod=755 docker/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
