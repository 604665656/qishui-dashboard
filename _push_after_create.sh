#!/bin/sh
# 仓库在网页上建好后，把 REMOTE_URL 换成你的仓库地址再执行
REMOTE_URL="$1"
if [ -z "$REMOTE_URL" ]; then echo "用法: sh _push_after_create.sh <仓库HTTPS地址>"; exit 1; fi
git remote remove origin 2>/dev/null
git remote add origin "$REMOTE_URL"
git branch -M main
git push -u origin main
echo "推送完成"
