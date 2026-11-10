from django import forms

from blog.models import Post


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["title", "category", "published_at", "content_md"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "content_md": forms.Textarea(
                attrs={"class": "form-control", "id": "md-input", "rows": 18, "style": "min-height: 420px"}
            ),
            # datetime-local 控件；带秒，避免编辑时丢秒
            "published_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local", "step": "1"},
                format="%Y-%m-%dT%H:%M:%S",
            ),
        }
        labels = {"title": "标题", "category": "分类", "published_at": "发布时间", "content_md": "正文（Markdown）"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 分类下拉样式 + 允许不选分类
        self.fields["category"].widget.attrs["class"] = "form-select"
        self.fields["category"].required = False
        # 编辑已有文章时按 datetime-local 需要的格式回填
        if self.instance and self.instance.pk:
            self.initial["published_at"] = self.instance.published_at.strftime("%Y-%m-%dT%H:%M:%S")
