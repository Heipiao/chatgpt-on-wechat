FROM ghcr.io/zhayujie/chatgpt-on-wechat:latest

# 清空基础镜像 /app 中的所有文件（含隐藏文件如 .git）
RUN rm -rf /app/* /app/.[!.]* /app/..?*
COPY . /app

# 安装新增依赖
RUN pip install --no-cache-dir "oss2>=2.18.0" -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

COPY --chmod=755 docker/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
