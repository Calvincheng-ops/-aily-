import json
import unittest

from aily_nodes.a7_build_archive_request import main as build_request
from aily_nodes.a9_build_file_confirm_card import main as build_file_card
from aily_nodes.b2_validate_callback import main as validate_callback
from aily_nodes.b_build_confirm_card import main as build_confirm_card
from aily_nodes.b_build_folder_card import main as build_folder_card
from aily_nodes.b_build_result_card import main as build_result_card


CHAT_ID = "oc_demo"
USER_ID = "ou_demo"
TRIGGER_ID = "om_trigger"
FILE_MESSAGE_ID = "om_file"


def mapping_payload(allowed_types=None):
    return {
        "code": 0,
        "data": {
            "items": [
                {
                    "record_id": "rec_mapping",
                    "fields": {
                        "enabled": True,
                        "chat_id": [{"text": CHAT_ID, "type": "text"}],
                        "chat_name": [{"text": "项目群", "type": "text"}],
                        "root_folder_token": [
                            {"text": "root_demo", "type": "text"}
                        ],
                        "root_folder_name": [
                            {"text": "项目归档", "type": "text"}
                        ],
                        "root_folder_url": {
                            "link": "https://example/root",
                            "text": "https://example/root",
                            "type": "url",
                        },
                        "allowed_file_types": (
                            ["pdf", "md"] if allowed_types is None else allowed_types
                        ),
                        "max_file_size_mb": 20,
                    },
                }
            ],
            "total": 1,
        },
    }


def trigger_payload(parent_id=FILE_MESSAGE_ID):
    return {
        "data": {
            "items": [
                {
                    "message_id": TRIGGER_ID,
                    "chat_id": CHAT_ID,
                    "msg_type": "text",
                    "parent_id": parent_id,
                    "root_id": parent_id,
                    "sender": {"sender_type": "user", "id": USER_ID},
                    "body": {"content": json.dumps({"text": "归档这个文件"})},
                }
            ]
        }
    }


def replied_file_payload(file_name="项目终版.md", file_size=0, sender_id=USER_ID):
    return {
        "data": {
            "items": [
                {
                    "message_id": FILE_MESSAGE_ID,
                    "chat_id": CHAT_ID,
                    "msg_type": "file",
                    "deleted": False,
                    "sender": {"sender_type": "user", "id": sender_id},
                    "body": {
                        "content": json.dumps(
                            {
                                "file_key": "file_key_demo",
                                "file_name": file_name,
                                "file_size": file_size,
                            }
                        )
                    },
                }
            ]
        }
    }


def valid_request_context():
    return build_request(
        mapping_payload(),
        trigger_payload(),
        replied_file_payload(),
        CHAT_ID,
        USER_ID,
        TRIGGER_ID,
        "归档这个文件",
        1000,
    )


class SkillANodeTests(unittest.TestCase):
    def test_directly_replied_single_file_builds_unselected_request(self):
        context = valid_request_context()

        self.assertTrue(context["ok"])
        self.assertEqual(context["candidate_count"], 1)
        self.assertEqual(context["file_name"], "项目终版.md")
        self.assertEqual(context["file_type"], "md")
        self.assertEqual(context["initial_status"], "selecting_file")
        self.assertEqual(context["selected_file_id"], "")
        self.assertEqual(context["selected_file_key"], "")
        self.assertEqual(context["expires_at_ms"], 1000 + 30 * 60 * 1000)

        candidates = json.loads(context["candidate_files_json"])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source_type"], "replied_message_file")
        self.assertEqual(candidates[0]["message_id"], FILE_MESSAGE_ID)

    def test_markdown_not_in_mapping_reports_file_type_error(self):
        context = build_request(
            mapping_payload(["pdf", "docx"]),
            trigger_payload(),
            replied_file_payload(),
            CHAT_ID,
            USER_ID,
            TRIGGER_ID,
            now_ms=1000,
        )

        self.assertFalse(context["ok"])
        self.assertEqual(context["error_code"], "FILE_TYPE_NOT_ALLOWED")
        self.assertIn(".md", context["error"])
        self.assertEqual(context["mapping_record_id"], "rec_mapping")
        self.assertEqual(context["root_folder_name"], "项目归档")

    def test_trigger_must_directly_reply_to_a_message(self):
        context = build_request(
            mapping_payload(),
            trigger_payload(parent_id=""),
            replied_file_payload(),
            CHAT_ID,
            USER_ID,
            TRIGGER_ID,
            now_ms=1000,
        )

        self.assertFalse(context["ok"])
        self.assertEqual(context["error_code"], "NOT_REPLY_TO_MESSAGE")

    def test_known_file_size_is_checked(self):
        mapping = mapping_payload()
        mapping["data"]["items"][0]["fields"]["max_file_size_mb"] = 1
        context = build_request(
            mapping,
            trigger_payload(),
            replied_file_payload("过大.pdf", 2 * 1024 * 1024),
            CHAT_ID,
            USER_ID,
            TRIGGER_ID,
            now_ms=1000,
        )

        self.assertFalse(context["ok"])
        self.assertEqual(context["error_code"], "FILE_TOO_LARGE")

    def test_single_upload_configuration_cannot_exceed_twenty_mb(self):
        mapping = mapping_payload()
        mapping["data"]["items"][0]["fields"]["max_file_size_mb"] = 21
        context = build_request(
            mapping,
            trigger_payload(),
            replied_file_payload(),
            CHAT_ID,
            USER_ID,
            TRIGGER_ID,
            now_ms=1000,
        )

        self.assertFalse(context["ok"])
        self.assertEqual(context["error_code"], "FILE_SIZE_CONFIG_UNSUPPORTED")

    def test_other_users_file_is_allowed_by_default(self):
        context = build_request(
            mapping_payload(),
            trigger_payload(),
            replied_file_payload(sender_id="ou_colleague"),
            CHAT_ID,
            USER_ID,
            TRIGGER_ID,
            now_ms=1000,
        )

        self.assertTrue(context["ok"])
        self.assertEqual(context["file_sender_id"], "ou_colleague")

    def test_sender_only_policy_can_be_enabled_per_mapping(self):
        mapping = mapping_payload()
        mapping["data"]["items"][0]["fields"][
            "only_file_sender_can_archive"
        ] = True
        context = build_request(
            mapping,
            trigger_payload(),
            replied_file_payload(sender_id="ou_colleague"),
            CHAT_ID,
            USER_ID,
            TRIGGER_ID,
            now_ms=1000,
        )

        self.assertFalse(context["ok"])
        self.assertEqual(context["error_code"], "FILE_SENDER_NOT_ALLOWED")

    def test_file_confirmation_button_passes_b_custom_parameters(self):
        context = valid_request_context()
        card = build_file_card(
            context["candidate_files_json"],
            context["request_id"],
            "skill_demo",
            context["requester_id"],
            context["root_folder_name"],
        )

        self.assertTrue(card["ok"])
        self.assertEqual(card["file_name"], "项目终版.md")
        skill_input = json.loads(card["skill_object_choose_file"]["skill_input"])
        self.assertEqual(skill_input["request_id"], context["request_id"])
        self.assertEqual(skill_input["action"], "choose_file")
        self.assertEqual(
            skill_input["selected_file_id"],
            context["candidate_file_id"],
        )
        self.assertTrue(card["skill_object_choose_file"]["update_card"])
        self.assertIn(
            "已确认文件",
            card["skill_object_choose_file"]["success_message"],
        )
        self.assertTrue(card["skill_object_cancel"]["update_card"])
        self.assertIn("已取消", card["skill_object_cancel"]["success_message"])


class SkillBNodeTests(unittest.TestCase):
    def _request_payload(self, context, **overrides):
        candidate = json.loads(context["candidate_files_json"])[0]
        fields = {
            "request_id": context["request_id"],
            "requester_id": USER_ID,
            "status": "selecting_file",
            "expires_at": 2_000_000,
            "candidate_files_json": context["candidate_files_json"],
            "root_folder_token_snapshot": "root_demo",
            "folder_path_json": json.dumps(
                [{"token": "root_demo", "name": "项目归档"}],
                ensure_ascii=False,
            ),
            "allowed_child_folders_json": json.dumps(
                [
                    {
                        "token": "folder_a",
                        "name": "A",
                        "parent_token": "root_demo",
                    }
                ],
                ensure_ascii=False,
            ),
            "selected_file_name": candidate["file_name"],
        }
        fields.update(overrides)
        return {
            "data": {
                "items": [
                    {
                        "record_id": "rec_request",
                        "fields": fields,
                    }
                ]
            }
        }

    def test_choose_file_is_validated_against_candidate_snapshot(self):
        context = valid_request_context()
        candidate = json.loads(context["candidate_files_json"])[0]
        result = validate_callback(
            self._request_payload(context),
            context["request_id"],
            "choose_file",
            USER_ID,
            candidate["id"],
            now_ms=1000,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            json.loads(result["selected_candidate_json"])["file_key"],
            "file_key_demo",
        )

    def test_browse_is_rejected_when_folder_is_not_in_whitelist(self):
        context = valid_request_context()
        result = validate_callback(
            self._request_payload(context, status="selecting_folder"),
            context["request_id"],
            "browse",
            USER_ID,
            selected_folder_token="folder_outside",
            now_ms=1000,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "INVALID_FOLDER_SELECTION")

    def test_operator_must_be_original_requester(self):
        context = valid_request_context()
        result = validate_callback(
            self._request_payload(context),
            context["request_id"],
            "cancel",
            "ou_other",
            now_ms=1000,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "OPERATOR_NOT_ALLOWED")

    def test_folder_card_filters_files_and_builds_whitelist(self):
        payload = {
            "data": {
                "data": {
                    "files": [
                        {
                            "type": "folder",
                            "token": "folder_a",
                            "name": "A",
                            "parent_token": "root_demo",
                        },
                        {
                            "type": "file",
                            "token": "file_a",
                            "name": "忽略.pdf",
                            "parent_token": "root_demo",
                        },
                    ]
                }
            }
        }
        result = build_folder_card(
            payload,
            "archive_demo",
            "项目终版.md",
            "root_demo",
            "项目归档",
            "https://example/root",
            '[{"token":"root_demo","name":"项目归档"}]',
            USER_ID,
            "",
            "skill_demo",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["folder_options"], [{"text": "A", "value": "folder_a"}])
        self.assertEqual(len(json.loads(result["allowed_child_folders_json"])), 1)
        for key in (
            "skill_object_browse",
            "skill_object_back",
            "skill_object_choose_current",
            "skill_object_cancel",
        ):
            self.assertTrue(result[key]["update_card"])
            self.assertTrue(result[key]["success_message"])

    def test_confirm_and_result_cards(self):
        confirm = build_confirm_card(
            "archive_demo",
            "skill_demo",
            USER_ID,
            "项目终版.md",
            "md",
            "项目归档 / 终版",
            "https://example/folder",
        )
        self.assertTrue(confirm["ok"])
        self.assertEqual(
            json.loads(confirm["skill_object_confirm"]["skill_input"])["action"],
            "confirm_upload",
        )
        self.assertTrue(confirm["skill_object_confirm"]["update_card"])
        self.assertIn(
            "正在上传",
            confirm["skill_object_confirm"]["success_message"],
        )
        for key in (
            "skill_object_return",
            "skill_object_cancel",
        ):
            self.assertTrue(confirm[key]["update_card"])
            self.assertTrue(confirm[key]["success_message"])

        result = build_result_card(
            "success",
            "archive_demo",
            USER_ID,
            "项目终版.md",
            "md",
            "终版",
            "项目归档 / 终版",
            "https://example/folder",
            "https://example/file",
            1024 * 1024,
            "2026-07-27 10:00",
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["is_success"])
        self.assertEqual(result["result_size_text"], "1.0 MB")


if __name__ == "__main__":
    unittest.main()
