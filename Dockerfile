FROM ghcr.io/zhayujie/chatgpt-on-wechat:latest

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]