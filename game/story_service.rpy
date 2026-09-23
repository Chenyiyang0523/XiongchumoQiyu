# 熊出没奇遇 — 故事服务边界
#
# 游戏默认使用本地故事引擎，无网络也能完整通关。
# 在开发/受控发布环境中，可通过环境变量配置 OpenAI 兼容代理：
#   XCMQY_AI_ENDPOINT  必须为 HTTPS（localhost 开发例外）
#   XCMQY_AI_KEY       可选的短期代理令牌，不得把服务商密钥打包进客户端
#   XCMQY_AI_MODEL     代理需要时指定的模型名

init python:
    import json as _story_json
    import os as _story_os
    import re as _story_re
    from urllib.parse import urlparse as _story_urlparse
    from urllib.request import Request as _StoryRequest, urlopen as _story_urlopen
    from urllib.error import HTTPError as _StoryHTTPError

    AI_ENDPOINT = _story_os.environ.get("XCMQY_AI_ENDPOINT", "").strip()
    AI_API_KEY = _story_os.environ.get("XCMQY_AI_KEY", "").strip()
    AI_MODEL = _story_os.environ.get("XCMQY_AI_MODEL", "deepseek-chat").strip()
    AI_MAX_RESPONSE_BYTES = 2 * 1024 * 1024

    def _story_log(message):
        """记录脱敏技术信息，不把请求正文、密钥或远端响应写入日志。"""
        try:
            renpy.log("[story-service] " + str(message))
        except Exception:
            pass

    def sanitize_player_text(value, limit=120, fallback=""):
        """对发往本地引擎或受控服务的用户输入做统一边界处理。"""
        text = str(value or "")
        text = _story_re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        text = _story_re.sub(r"\s+", " ", text).strip()
        if limit and len(text) > limit:
            text = text[:limit].rstrip()
        return text or fallback

    def _validated_ai_endpoint():
        if not AI_ENDPOINT:
            return ""
        parsed = _story_urlparse(AI_ENDPOINT)
        host = (parsed.hostname or "").lower()
        is_local = host in ("localhost", "127.0.0.1", "::1")
        if parsed.scheme == "https" and host:
            return AI_ENDPOINT
        if parsed.scheme == "http" and is_local:
            return AI_ENDPOINT
        return ""

    def ai_service_configured():
        """只表示开发者已配置受控端点；玩家仍需在本次冒险中显式选择联网。"""
        return bool(_validated_ai_endpoint())

    def use_online_story(game_ref):
        return bool(
            game_ref is not None
            and getattr(game_ref, "online_enabled", False)
            and ai_service_configured()
        )

    def _online_request(messages, stream=False):
        """Perform one strict-TLS, size-bounded OpenAI-compatible request."""
        endpoint = _validated_ai_endpoint()
        if not endpoint:
            raise ValueError("AI endpoint is not configured or is not secure")

        payload_data = {
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 900,
            "stream": bool(stream),
        }
        if AI_MODEL:
            payload_data["model"] = AI_MODEL

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "User-Agent": "XiongchumoQiyu/1.1",
        }
        if AI_API_KEY:
            headers["Authorization"] = "Bearer " + AI_API_KEY

        request = _StoryRequest(
            endpoint,
            data=_story_json.dumps(payload_data, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        # 不提供任何证书校验降级路径。证书失败即转本地故事。
        response = _story_urlopen(request, timeout=60)
        try:
            if not stream:
                raw = response.read(AI_MAX_RESPONSE_BYTES + 1)
                if len(raw) > AI_MAX_RESPONSE_BYTES:
                    raise ValueError("AI response exceeds size limit")
                data = _story_json.loads(raw.decode("utf-8"))
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                content = str(content or "").strip()
                if not content:
                    raise ValueError("AI returned an empty response")
                return content[:12000]

            chunks = []
            byte_count = 0
            saw_done = False
            for raw_line in response:
                byte_count += len(raw_line)
                if byte_count > AI_MAX_RESPONSE_BYTES:
                    raise ValueError("AI stream exceeds size limit")
                line = raw_line.decode("utf-8", errors="strict").strip()
                if not line or not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    saw_done = True
                    break
                chunk = _story_json.loads(body)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    chunks.append(str(content))
            result = "".join(chunks).strip()
            if not saw_done or not result:
                raise ValueError("AI stream ended before a valid completion")
            return result[:12000]
        finally:
            try:
                response.close()
            except Exception:
                pass

    def _supporting_character(game_ref):
        player = getattr(game_ref, "character", "") if game_ref else ""
        for candidate in ("熊大", "熊二", "赵琳", "光头强"):
            if candidate != player:
                return candidate
        return "熊大"

    def _local_choice_effect(user_text):
        code = local_choice_code(user_text)
        if "独自" in str(user_text):
            return {"勇": 1, "友": -2}, "你的行动很快，但伙伴也需要被照顾"
        if code == "B":
            return {"勇": 1, "体": 1}, "动手解决问题"
        if code == "C":
            return {"友": 2}, "和伙伴一起完成任务"
        return {"智": 1, "友": 1}, "先观察，再判断"

    def build_local_story(game_ref):
        return build_campaign_story(game_ref)

    def _local_score(game_ref):
        stats = getattr(game_ref, "stats", {}) or {}
        values = [max(0, min(10, int(stats.get(k, 5)))) for k in ("智", "勇", "体", "友")]
        average = sum(values) / 4.0
        turns = max(0, int(getattr(game_ref, "turn_count", 0) or 0))
        expected = max(1, int(getattr(game_ref, "max_turns", 1) or 1))
        participation = min(1.0, turns / float(expected))
        return max(60, min(100, int(round(45 + average * 4 + participation * 15))))

    def build_local_evaluation(game_ref):
        responses = list(getattr(game_ref, "user_responses", []) or [])
        first = sanitize_player_text(responses[0] if responses else "", 50, "体验了故事开场")
        last = sanitize_player_text(responses[-1] if responses else "", 50, first)
        stats = getattr(game_ref, "stats", {}) or {}
        labels = {"智": "智慧", "勇": "勇气", "体": "体力", "友": "友谊"}
        strongest = max(("智", "勇", "体", "友"), key=lambda k: int(stats.get(k, 5)))
        growth = min(("智", "勇", "体", "友"), key=lambda k: int(stats.get(k, 5)))
        score = _local_score(game_ref)
        title = "{}{}".format(labels[strongest], "小队长" if strongest != "友" else "守护者")
        ending_title, ending_kind, ending_summary = local_ending(game_ref)
        return """**角色表现**
你完成了{turns}轮互动。从“{first}”到“{last}”，每次选择都真正推动了故事。

**亮点时刻**
本次最突出的是{strongest}，这来自你在观察、行动和合作中的累积，不是一个标签。

**下次挑战**
下次可以多试试与{growth}有关的选择，看看故事会怎样变化。

**总评**
综合评分：{score}/100分
专属称号：{title}
一句话鼓励：好奇心和善意，是每次冒险最好的装备！

**结局档案**
结局标题：{ending_title}
结局类型：{ending_kind}
一句话概括：{ending_summary}""".format(
            turns=len(responses), first=first, last=last,
            strongest=labels[strongest], growth=labels[growth], score=score,
            title=title, ending_title=ending_title, ending_kind=ending_kind, ending_summary=ending_summary,
        )

    def build_local_parent_report(game_ref):
        responses = list(getattr(game_ref, "user_responses", []) or [])
        example = sanitize_player_text(responses[-1] if responses else "", 60, "本次主要体验了开场")
        stats = getattr(game_ref, "stats", {}) or {}
        summary = "、".join("{}{}".format(k, max(0, min(10, int(stats.get(k, 5))))) for k in ("智", "勇", "体", "友"))
        return """**家庭共读记录**

**数据概览**
本次共完成{turns}轮互动，结束时的游戏属性为：{summary}。这些数值只是故事内的反馈，不是能力或心理测评。

**本次观察**
孩子最后一次回应是“{example}”。可以围绕这个选择询问“你当时看到了什么线索”和“还有别的办法吗”，帮助孩子讲清自己的思考。

**共玩记录**
{family_note}

**共玩建议**
下次可让孩子先选，家长再提一个不同方案，一起预测两种结果。关注孩子愿意说出理由的过程，无需追求唯一正确答案。

**说明**
本记录仅根据这一次游戏内的有限选择生成，不应用于诊断、评估或比较孩子。""".format(
            turns=len(responses), summary=summary, example=example,
            family_note=getattr(game_ref, "family_discussion", "") or "本次未进行亲子讨论，可以在结束后一起聊聊选择的理由。",
        )

    def _fallback_for_purpose(game_ref, purpose):
        if purpose == "evaluation":
            return build_local_evaluation(game_ref)
        if purpose == "parent_report":
            return build_local_parent_report(game_ref)
        return build_local_story(game_ref)

    def call_ai(messages, game_ref=None, purpose="story"):
        """非流式边界：仅在玩家选择联网且端点合法时请求，任何失败均安全降级。"""
        if use_online_story(game_ref):
            try:
                return _online_request(messages, stream=False)
            except _StoryHTTPError as error:
                _story_log("online HTTP error {} for {}".format(error.code, purpose))
            except Exception as error:
                _story_log("online {} failed: {}".format(purpose, type(error).__name__))
            if game_ref is not None:
                game_ref.ai_notice = "云端故事暂时不可用，已安全切换到本地模式。"
        return _fallback_for_purpose(game_ref, purpose)

    def _commit_story_response(game_ref, response, request_epoch):
        if request_epoch != getattr(game_ref, "_request_epoch", None):
            return False
        parsed = parse_ai_response(response)
        visible = [s for s in parsed if s and s[0] in ("scene", "dialogue", "narration", "text")]
        if not visible:
            response = build_local_story(game_ref)
            parsed = parse_ai_response(response)
            game_ref.ai_notice = "故事响应格式不完整，已改用本地剧情继续。"
        game_ref._full_response = response
        game_ref._stream_buffer = ""
        game_ref.ai_result = response
        for segment in parsed:
            game_ref._segment_queue.append(segment)
        return True

    def call_ai_stream(messages, game_ref, request_epoch):
        """
        先在后台完整验证远端 SSE，再一次性提交到游戏队列。
        这避免断网时把半截故事写入存档和上下文。
        """
        if request_epoch != getattr(game_ref, "_request_epoch", None):
            return
        if use_online_story(game_ref):
            try:
                response = _online_request(messages, stream=True)
            except _StoryHTTPError as error:
                _story_log("online stream HTTP error {}".format(error.code))
                response = build_local_story(game_ref)
                game_ref.ai_notice = "云端故事暂时不可用，已安全切换到本地模式。"
            except Exception as error:
                _story_log("online stream failed: {}".format(type(error).__name__))
                response = build_local_story(game_ref)
                game_ref.ai_notice = "云端故事暂时不可用，已安全切换到本地模式。"
        else:
            response = build_local_story(game_ref)
        _commit_story_response(game_ref, response, request_epoch)
