UPDATE source_materials
SET name = 'Qsheep 留学账号'
WHERE type = 'account_profile'
  AND name IN ('Account Profile', '账号概况', 'Profile')
  AND text_content LIKE '%@QSheep%';

UPDATE source_materials
SET name = '留学帖子数据合集'
WHERE type = 'historical_posts'
  AND name IN ('历史笔记', 'Historical Posts', 'historical_posts')
  AND (
    text_content LIKE '%留学中介到底值不值%'
    OR text_content LIKE '%二本逆袭G5%'
  );

UPDATE source_materials
SET name = '留学评论区合集'
WHERE type = 'comments'
  AND name IN ('评论样本', 'Comments', 'comments')
  AND (
    text_content LIKE '%双非背景冲英国前30%'
    OR text_content LIKE '%中介那部分太真实%'
  );

UPDATE source_materials
SET name = '数字游民趋势.csv'
WHERE type = 'trend_csv'
  AND name IN ('趋势 CSV', 'Trend CSV', 'trend.csv', '数字游民热帖')
  AND keyword = '数字游民';

UPDATE source_materials
SET name = 'AI短剧创作者样本'
WHERE type = 'video_creator_samples'
  AND name IN ('视频创作者样本', 'Video Creator Samples', 'video_creator_samples')
  AND (
    text_content LIKE '%AI短剧研究所%'
    OR text_content LIKE '%机器人女友觉醒%'
  );
