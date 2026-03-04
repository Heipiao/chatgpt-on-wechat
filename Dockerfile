FROM ghcr.io/zhayujie/chatgpt-on-wechat:latest

# 完全清空基础镜像的 /app，用本地代码替换
RUN rm -rf /app
COPY . /app

# 安装新增依赖
RUN pip install --no-cache-dir "oss2>=2.18.0" -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

COPY --chmod=755 docker/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
