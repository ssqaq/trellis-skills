# 自动更新所需的发布包

这是维护者的发布约定。普通用户按首页安装和使用即可。

1. 使用正式三段版本号，例如 `v1.4.0`，并保持包内 `VERSION` 和 `skills/trellis-setup/VERSION` 一致。自动更新忽略草稿、预发布版和低于本机的版本。
2. Release 上传 `trellis-skills-1.4.0.zip` 和 `trellis-skills-1.4.0.zip.sha256`；后续版本替换其中的版本号。GitHub 自动生成的 Source code 下载项不能替代这两个附件。
3. ZIP 里只放一个顶层目录 `trellis-skills-1.4.0/`，包含完整技能、安装/同步/卸载程序及版本文件。可从已验证提交生成：

   ```text
   git archive --format=zip --prefix=trellis-skills-1.4.0/ --output=trellis-skills-1.4.0.zip <已验证的提交>
   ```

4. 校验文件使用纯文本，内容为64位SHA256、两个空格、ZIP文件名。附件完整上传后再将正式 Release 设为 Latest，并核对线上附件摘要。
5. 每次发版前运行完整 Python 回归、PowerShell 同步集成和技能格式校验。升级行为有变化时，按 `tests/prepare_live_update.py` 建立隔离环境做真实 Codex 任务验证；本地模拟版本不发布到 GitHub。

自动更新会拒绝缺少附件、校验失败、包内版本不符和缓存内容被改动的包。检测失败只影响升级，不中断用户的开发任务。用户配置目录保留实际安装版本、待更新项目及恢复备份，不能用下载成功代替安装验收。
