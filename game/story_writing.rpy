# UI bridge only. Linux prompts and writing code remain verbatim in xcmengine.
init python:
    import linux_story as _linux_story

    def random_story_scenario(online=False):
        if online:
            return renpy.random.choice(_linux_story.load_content().seeds["cards"])["hook"]
        return renpy.random.choice(EXAMPLE_SCENARIOS)

    def build_lean_story_prompt(game_ref):
        return _linux_story.prompts.system_lean(_linux_story.load_content())

    def lean_turn_prompt(game_ref, player_input=None, qte_result=None):
        # This is a readable UI transcript, never the writer's request context.
        return player_input if player_input is not None else "请开始这个精彩的故事：" + game_ref.scenario

    def linux_story_client():
        return _linux_story.client_for(_validated_ai_endpoint(), AI_API_KEY)

    def request_linux_story(game_ref, request_epoch=None):
        epoch = game_ref._request_epoch if request_epoch is None else request_epoch
        if getattr(game_ref, "_story_writer", "") != "linux-lean":
            raise ValueError("This saved story predates the Linux writer")

        def save(state):
            if game_ref._request_epoch == epoch:
                game_ref._linux_state = state

        class EpochCancel:
            @property
            def cancelled(self):
                return game_ref._request_epoch != epoch

        view = _linux_story.generate(
            getattr(game_ref, "_linux_state", None), game_ref.scenario, game_ref.duration,
            game_ref.run_id, game_ref.turn_count,
            game_ref.user_responses[-1] if game_ref.user_responses else None,
            linux_story_client(), save, EpochCancel())
        if game_ref._request_epoch != epoch:
            return ""
        game_ref._linux_view = view
        return view["text"]

    def story_options(game_ref):
        if game_ref.online_enabled and getattr(game_ref, "_story_writer", "") == "linux-lean":
            return getattr(game_ref, "_linux_view", {}).get("options", [])
        return extract_options(game_ref._full_response)
