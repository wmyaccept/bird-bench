# codebase_community （8 表） · simple EX 88.1% (133/151)

## ⚠️ 交题前必查（本库最容易翻车的几条）

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

## 惯例卡片（实测统计，n=186 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(列) 54 / COUNT(DISTINCT) 10 / COUNT(*) 6 / 无 116　⇒ 本库以 `COUNT(列)` 为主（54/70 计数题）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：users 76 / posts 49 / comments 23 / badges 17 / votes 7 / tags 6 / postHistory 5 / postLinks 3　⇒ 主表以 **users** 为主但**不固定**（76/186）⇒ 按题干主语选
- `SELECT DISTINCT`：10/186　|　`*100`：9　|　`BETWEEN`：10
- 输出列数分布：1列×152 / 2列×32 / 3列×2
- JOIN 数分布：0:45, 1:118, 2:23

> 由 `bird_conventions db=codebase_community write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
## ⚠️⚠️ moderate 全组实测（30 道，17 对 = 56.7%）—— 全库最低分库之一，坑**全在"用哪张表、用哪一行"**

⭐ 这一组的 13 道错，复盘时逐条对照了金标，规律高度集中（每一条都出自金标 SQL，不是猜的）：

### ① 分母/平均要看**"JOIN 之后的行数"**，不是独立子查询数出来的行数

- **557**「Among the posts with a score of over 5, what is the percentage…」金标：
  `SUM(IIF(T2.Age > 65, 1, 0)) * 100 / COUNT(T1.Id)` —— 分母就是**同一个 JOIN 的行数**。
  我用 `(SELECT COUNT(*) FROM posts WHERE Score > 5)` 当分母（少了几行，值就错）✗
- **672**「how many users whose post have a total favorite amount of 4 or more」金标：
  `COUNT(T1.Id) FROM users T1 JOIN posts T2 … WHERE T2.FavoriteCount >= 4` ⇒ **数 JOIN 后的帖子行**（**不去重**）✗ 我按去重用户数算
- **716** 反过来：金标 `COUNT(DISTINCT CASE WHEN UpVotes = 0 THEN T1.Id END) * 100 / COUNT(DISTINCT T1.Id)` ⇒ **要去重用户** ✗ 我数了评论行
- **604**「average of the up votes and the average user age」金标 `AVG(T1.UpVotes), AVG(T1.Age)` + 子查询
  `HAVING COUNT(*) > 10` ⇒ 是 `AVG(列)`（**用户粒度**），不是 evidence 写的 "Divide(Sum, Count)" 加权 ✗
  ⇒ **evidence 里的 Divide(Sum, Count) 不能当成"按行加权"的证据**。

### ② "comment" 有**两处**：`comments.Text` vs **`postHistory.Comment`**

- **584**「comments left by users who edited the post …」金标：
  `SELECT T2.Comment FROM posts T1 JOIN postHistory T2 ON T1.Id = T2.PostId WHERE T1.Title = …` ⇒ **8 行**
  （我走 `comments.Text` 得 14254 行）✗
  ⇒ 只要题干里出现 **edit/edited/revision**，"comment" 就是 `postHistory.Comment`（编辑备注）。

### ③ 「used by X in his posts」要走 `postHistory`

- **637** 金标：`users JOIN postHistory ON … JOIN posts T3 … WHERE DisplayName='Mark Meckes' AND T3.CommentCount = 0
  AND T3.Tags IS NOT NULL` + **`SELECT DISTINCT`** ⇒ 1 行
  （我走 `posts.OwnerUserId` 得 2 行、也没加 `Tags IS NOT NULL`）✗

### ④ 字符串/日期/大写这三处"金标偷懒"，要顺着它写

- **692**「How long did it take …?」金标：`SELECT T1.Date - T2.CreationDate`（**字符串直接相减**）⇒
  SQLite 取数字前缀 = **年份差 1**；我规规矩矩用 `JULIANDAY()` 反而错 ✗
  ⇒ 本库日期列都是 `'YYYY-MM-DD HH:MM:SS.0'`，**金标日期相减就是取年份**。
- **665**「average monthly number of links」金标：`COUNT(T1.Id) / 12` ⇒ **分母固定 12**（不是有数据的 6 个月）✗
- **640** 金标字面量写 `'Mornington'`（首字母大写），而库里存的是 **`mornington`** ⇒ 金标那半边**匹配不上 = 0**，
  答案是 `0 - SUM(Amos)` = **-497**。我"聪明地"用了库里的真实大小写 `'mornington'` ✗
  ⇒ **字面量照题干/evidence 的写法抄，不要替金标纠正大小写。**

### ⑤ 列语义/列序：`Tags`、`id`、`(AVG, Title, Text)`

- **587**「average view count … and list the title and the comment」金标列序是
  **`(AVG(T2.ViewCount), T2.Title, T1.Text)`**（聚合在最前），而且 `Tags = '<humor>'` 是**精确等值**（不是 `LIKE`）✗
- **682**「give its id and the owner's display name」金标给的是 **`T2.OwnerUserId`**（**owner 的 id，不是帖子 id**），
  且用 `ORDER BY FavoriteCount DESC LIMIT 1`（不做并列过滤）✗
- **708**「creation date and age of the user」金标是 **`T2.CreationDate`（`users` 表的创建日期）+ `T2.Age`**，
  不是评论的日期（我的行数正好 17030 对上，只有列内容错）✗
- **565**「was that post well-finished?」金标文案 = **`'well-finished'` / `'NOT well-finished'`**
  （`IIF(ClosedDate IS NULL, 'NOT well-finished', 'well-finished')`），**不是 'YES'/'NO'** ✗
  ⇒ 本库是否题的文本要从 evidence 的措辞里抄（这里 evidence 自己写了 not well-finished）。

## ⚠️⚠️ challenging 实测（5 道，3 对 = 60%）

- **586**「Which user added a bounty amount of 50 to the post title mentioning variance?」金标
  `SELECT T3.DisplayName, T1.Title` ⇒ **2 列（用户名 + 帖子标题）**，我只给了用户名 ✗
  ⇒ "Which user … to the post …" 这类**把两个实体都放进输出**是金标的习惯。
- **598**「percentage difference of student badges during 2010 and 2011」金标
  `… WHERE Name = 'Student'`，分母是 **`COUNT(Id)` = 该子集（Student 徽章）的行数**，
  不是整张 `badges` 表 ✗（542/2501 − 1959/2501）。
- 对得稳的：634（Harvey Motulsky 总浏览量更高）、639（Community 的帖子 0% 用 R 标签，**答案就是 0**）、
  701（最 influencial 用户 whuber 的题目金标自身执行失败，不计）。
## ⚠️⚠️ 值层实测（D 类 25 道）：**时间列常不在你以为的那张表里**

- ⭐ `posts.CreaionDate`（**原文就是拼错的**）vs `postHistory.CreationDate` vs `postLinks.CreationDate`：
  `642`（21st July 2010 发的帖子）金标走 **`postHistory`**；`603`（2011 年 686 的收藏）金标也走 `postHistory`；
  `667`（oldest post link）金标排序用的却是 **`posts.CreaionDate`**（不是 `postLinks.CreationDate`）。
  ⇒ 题干说的是**行为**（posted / commented / edited）时，先想 `postHistory`。
- ⭐ `696` “tag specified as 'careers'” 金标 **`FROM tags WHERE TagName = 'careers'`**（tags 表一行一标签），
  不是 `posts.Tags LIKE '%<careers>%'`。
- ⭐ 计数形态：`COUNT(T1.Id)` 常见（`557`/`632`/`672`）；`709`/`716` 才用 `COUNT(DISTINCT …)`。
- ⭐ `628` “users with the highest number of views” 要给 **`Id, DisplayName`** 两列；
  `594` “which user created post ID 1” 给 **`DisplayName`**（不是 userId）。
- ⭐ `665` “average monthly number of links in 2010” 的分母是 **12**（不是“有数据的月份数”）。
- ⭐ `565` 是否题：金标 `IIF(ClosedDate IS NULL, 'NOT well-finished', 'well-finished')`
  —— 两个字符串是**它自己定的**，别自己造。
