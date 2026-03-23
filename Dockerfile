FROM ghcr.io/zhayujie/chatgpt-on-wechat:latest

# 清空基础镜像 /app 中的所有文件（含隐藏文件如 .git）
RUN rm -rf /app/* /app/.[!.]* /app/..?*
COPY --chmod=0777 . /app
COPY --chmod=755 docker/entrypoint.sh /entrypoint.sh

# 用 root 安装依赖并创建用户
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir oss2 PyMySQL \
    && mkdir -p /home/noroot \
    && groupadd -r noroot 2>/dev/null || true \
    && useradd -r -g noroot -s /bin/bash -d /home/noroot noroot 2>/dev/null || true \
    && chown -R noroot:noroot /home/noroot /app /entrypoint.sh

# 切回普通用户
USER noroot

ENTRYPOINT ["/entrypoint.sh"]
