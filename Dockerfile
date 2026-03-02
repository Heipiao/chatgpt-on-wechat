FROM ghcr.io/zhayujie/chatgpt-on-wechat:latest

# 复制时直接赋予可执行权限，避免 RUN chmod 在基础镜像中失败
COPY --chmod=755 docker/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]