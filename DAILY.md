# Daily Briefing: morning update steps

Work in this folder (`~/Documents/daily-briefing`). Do these steps in order.

## 1. Fetch today's material
```bash
python3 update.py fetch
```
This saves headlines and each channel's newest video to `data/fetched.json`
and prints which videos still need a summary.

## 2. Write summaries for the new videos
For each video it lists, add an entry to `data/summaries.json`, keyed by the
video id:

```json
"VIDEO_ID": {
  "headline": "A clear, neutral headline (max ~90 characters)",
  "summary": "Paragraph one.\n\nParagraph two.\n\nParagraph three.",
  "basis": "description"
}
```

Sources you may use, from best to weakest:
1. The video's transcript, if one is saved in `data/transcripts/VIDEO_ID.txt`.
   If you used it, set `"basis": "transcript"`.
2. The video's own title and description in `data/fetched.json`.
3. The channel's own official companion page for the same episode (for
   example its Substack post or podcast listing), found with a web search.

Rules:
- Neutral tone. Report what the speakers say or claim ("X argues that…",
  "according to the guest…"). Don't endorse or rebut them.
- Write 3–5 paragraphs when the sources contain enough detail. When they
  don't (for example a description that only repeats the title), write a
  shorter summary and say plainly that little detail was available.
  **Never invent content** that isn't in the sources.
- Don't copy long passages. Keep any quote under 15 words.
- Keep entries for older videos; never delete them.

## 3. Rebuild the page
```bash
python3 update.py build
```
It should print `index.html updated.` with no missing summaries.

## 4. Publish
If this folder is a Git repository with a remote:
```bash
git add -A && git commit -m "Daily update $(date +%F)" && git push
```

## 5. Report
In 3–4 lines, say what was updated, any errors from step 1, and anything
that needs the owner's attention.
