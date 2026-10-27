# Robin-pet 仓库维护

仓库：https://github.com/nyxianlihai-lgtm/Robin-pet

当前仓库只分发通用代码、MIT 许可、素材使用说明、manifest 示例和几何占位图。角色参考图片、视频、动作帧包和创作过程归档保留本地，不再上传；具体边界见 ASSETS.md。

## 后续更新

```powershell
git -C "E:\Codex\create-pet" add .
git -C "E:\Codex\create-pet" diff --cached --stat
git -C "E:\Codex\create-pet" commit -m "Describe the change"
git -C "E:\Codex\create-pet" push
```

提交前确认不包含 data、个人 API 配置、参考图、视频或生成帧。将自备素材放在 data/pet-assets 或 user-assets，保持 Git 忽略规则。不要使用强制 add 绕过素材排除规则。

## 历史清理后

main 和 v1.0 的素材历史已通过 git-filter-repo 重写。旧克隆请重新克隆，不要将旧 main 合并回新仓库。清理前的备份只保存在本地 data/history-before-cleanup.git，不应上传。

版本页面只能附加代码包；不附加角色图片、演示录像或完整帧包。若遇到权利反馈，通过相关联系渠道处理。

GitHub 的旧 SHA 缓存、其他人的 fork 和已下载副本可能仍保留历史内容；普通强推无法回收这些副本。
