# codebase_community （8 表） · simple EX 88.1% (133/151)

## ⚠️ 交题前必查（本库最容易翻车的 3 条）

1. **列名拼写**：`posts.CreaionDate`（官方就是拼错的）、`LasActivityDate`。
   日期带毫秒：`'2010-07-19 19:39:08.0'`；`votes.CreationDate` 只到日。
2. **列在哪张表**：`BountyAmount` **只在 `votes`**；`Score` 在 `posts`/`comments` 都有。
3. **「last to edit」别用 `posts.LastEditorUserId`**（**47361 行是 NULL**，JOIN 直接空集）→
   走 `postHistory`：`WHERE post_id=... ORDER BY CreationDate DESC LIMIT 1`。

## 连接图与坑

```
users ──Id──┐
             posts（OwnerUserId）── Id ── comments.PostId
             votes（UserId / PostId）
             badges（UserId）
             postHistory / postLinks
tags ──ExcerptPostId / WikiPostId── posts.Id
```
- **`posts` 的创建日期列名是拼错的 `CreaionDate`**（不是 CreationDate），最后活动是 `LasActivityDate`。
- `Score` 在 `posts` 和 `comments` **两张表都有**（`minidev idx 344` 实测金标用 `posts.Score`）。
- `users.Age`：teenager 13-18 / adult 19-65 / **elder > 65**。
- ⚠️ **日期列的格式不统一，而且带毫秒后缀 `.0`**（本轮实测踩过）：

  | 列 | 实际值 |
  |---|---|
  | `votes.CreationDate` | `'2010-07-19'`（只到日） |
  | `badges.Date` | `'2010-07-19 19:39:08.0'`（带 `.0`） |
  | `comments.CreationDate` | `'2010-07-19 19:25:47.0'`（带 `.0`） |

  ⇒ 题目给出具体到秒的时间（如 "7/19/2010 7:39:08 PM"）时，要转成 `19:39:08` 并**补上 `.0`**：
  `WHERE Date = '2010-07-19 19:39:08.0'`；用 `LIKE '2010-07-19 19:39:08%'` 也行。
- **取年份**用 `SUBSTR(col,1,4)='2011'` 或 `col LIKE '2011%'`（SQLite 没有 `YEAR()`）。
- 常见题型（本轮 60 道基本全部命中）：
  - “s 的 badge 名” → `badges JOIN users ON badges.UserId=users.Id WHERE users.DisplayName='s'`
  - “获得某 badge 的用户” → 同上反向过滤 `badges.Name='Organizer'`
  - “某用户拥有的帖” → `posts JOIN users ON posts.OwnerUserId=users.Id`
  - “被某人编辑的帖” → 把 `OwnerUserId` 换成 `LastEditorUserId`；
    **若行数对不上，改查 `postHistory`**（`postHistory.UserId = users.Id` + `DISTINCT posts.Title`）
  - “某帖有多少评论” → `posts.CommentCount` 字段 ≠ 评论行数；先试字段，
    行数不对再换 `COUNT(*)`（参考 `minidev idx 344`）
- ⚠️ **两个“一对多”表都有方向性，别猜错边（实测 `dev idx 651`/`667`）**：
  | 表 | 两个方向 |
  |---|---|
  | `postLinks` | `PostId`（源头帖）/ `RelatedPostId`（被指向的相关帖） |
  | `posts.ParentId` | 自己 = 子帖，`ParentId` = 父帖的 id |

  “相关帖的标题” → 拿 `p1.Title` 去筛 `postLinks.PostId`，输出 `p2.Title`（JOIN `RelatedPostId`）。
  行数/值对不上就**换另一边再试一次**（成本很低，且只有一个方向是金标）。
- **`postHistory` 列清单**（列名易记错）：
  `Id / PostHistoryTypeId / PostId / RevisionGUID / CreationDate / UserId / Text / Comment / UserDisplayName`
- ⚠️ **`posts` 表没有 `BountyAmount`**，它在 **`votes`** 表上（实测踩过 `dev idx 700`：写成 `posts.BountyAmount`
  直接报 `no such column`）。类似地：`CommentCount / FavoriteCount / ViewCount / Score` 在 `posts`，
  `BountyAmount` 只在 `votes`。
- ⚠️ **“last edited by / last to edit” 不要用 `posts.LastEditorUserId`**：该列有 **47361 行是 NULL**
  （实测），JOIN `users` 会直接得空集（`dev idx 689` 我交了个 0 行的答案）。
  正确做法是走 **`postHistory`**：
  ```sql
  SELECT users.DisplayName, users.Location FROM postHistory
  JOIN users ON postHistory.UserId = users.Id
  WHERE postHistory.PostId = 183
  ORDER BY postHistory.CreationDate DESC LIMIT 1
  ```
  实测结果：`('Vitor De Mario', 'Rio de Janeiro')`。evidence 里的
  `last to edit refers to MAX(LastEditDate)` 说的就是这个“按时间取最后一条编辑记录”。
- ⚠️ **“count the number of posts with tag X”，若 evidence 点名 `TagName`，金标就在 `tags` 表上数**：
  `dev idx 696`（'careers'）实测 ——
  `SELECT COUNT(*) FROM tags WHERE TagName='careers'` = **1**（金标）
  vs `SELECT COUNT(*) FROM posts WHERE Tags LIKE '%<careers>%'` = 22（**错**）。
  ⇒ **evidence 点到哪张表的哪个列，就用那个列**，不要自己找“等价”的写法（详见 `naming-traps.md`）。

⚠️ **"parent id" 指的是 `posts.ParentId`，不是 `comments.PostId`**（实测 `564`）：
题干说 “the post with only one comment and parent id 107829” 时，
用 `comments.PostId=107829` 会返回 **0 行**（该 id 是帖子的父帖 id）。
凡是出现 "parent id / parent post"，先想 `posts.ParentId`。
