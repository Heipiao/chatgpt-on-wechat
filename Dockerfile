FROM ghcr.io/zhayujie/chatgpt-on-wechat:latest

# 清理基础镜像中可能冲突的 .git 目录
RUN rm -rf /app/.git

# 用本地代码覆盖基础镜像中的 /app
COPY . /app

# 安装新增依赖（oss2 等）
RUN pip install --no-cache-dir oss2>=2.18.0 -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制时直接赋予可执行权限
COPY --chmod=755 docker/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
