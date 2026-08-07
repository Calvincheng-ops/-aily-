import json
import unittest
from unittest import mock

from aily_nodes.a2_normalize_trigger_message import main as normalize_trigger
from aily_nodes.a7_build_archive_request import main as build_request
from aily_nodes.a9_build_file_confirm_card import main as build_file_card
from aily_nodes.b0_prepare_request_filter import main as prepare_request_filter
from aily_nodes.b2_validate_callback import main as validate_callback
from aily_nodes.b3_prepare_action import main as prepare_action
from aily_nodes.b5_validate_processing_request import (
    main as validate_processing_request,
)
from aily_nodes.b6_validate_upload_policy import main as validate_upload_policy
from aily_nodes.b8_compute_actual_size import main as compute_actual_size
from aily_nodes.b9_download_and_upload import main as download_and_upload
from aily_nodes.b_build_confirm_card import main as build_confirm_card
from aily_nodes.b_build_folder_card import main as build_folder_card
from aily_nodes.b_build_result_card import main as build_result_card
from aily_nodes.common_now_ms import main as current_time
from aily_nodes.common_build_url_object import main as build_url_object


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
    def test_url_object_helper_builds_base_link_cell(self):
        result = build_url_object("https://example/file", "项目终版.md")

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["url_object"],
            {
                "text": "项目终版.md",
                "link": "https://example/file",
            },
        )

    def test_trigger_message_normalizer_builds_base_filter_array(self):
        normalized = normalize_trigger(
            {
                "code": "200",
                "data": {
                    "code": 0,
                    "data": {
                        "items": trigger_payload()["data"]["items"],
                    },
                    "msg": "success",
                },
                "message": "OK",
            },
            TRIGGER_ID,
        )

        self.assertTrue(normalized["ok"])
        self.assertEqual(normalized["chat_id"], CHAT_ID)
        self.assertEqual(normalized["chat_id_filter_values"], [CHAT_ID])
        self.assertEqual(normalized["parent_id"], FILE_MESSAGE_ID)
        self.assertEqual(normalized["sender_id"], USER_ID)

    def test_trigger_message_normalizer_does_not_guess_wrong_message(self):
        normalized = normalize_trigger(trigger_payload(), "om_not_present")

        self.assertFalse(normalized["ok"])
        self.assertEqual(
            normalized["error_code"],
            "TRIGGER_MESSAGE_NOT_FOUND",
        )

    def test_common_time_node_returns_unix_milliseconds(self):
        value = current_time()["now_ms"]
        self.assertGreater(value, 1_000_000_000_000)

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
        self.assertEqual(
            context["root_folder_url_object"],
            {
                "text": "项目归档",
                "link": "https://example/root",
            },
        )
        self.assertEqual(
            context["current_folder_url_object"],
            context["root_folder_url_object"],
        )

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
    def test_request_filter_adapter_keeps_scalar_and_builds_array(self):
        result = prepare_request_filter(" archive_demo ")

        self.assertTrue(result["ok"])
        self.assertEqual(result["request_id"], "archive_demo")
        self.assertEqual(
            result["request_id_filter_values"],
            ["archive_demo"],
        )

    def test_request_filter_adapter_rejects_empty_id(self):
        result = prepare_request_filter("")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "REQUEST_ID_MISSING")
        self.assertEqual(result["request_id_filter_values"], [])

    def _request_payload(self, context, **overrides):
        candidate = json.loads(context["candidate_files_json"])[0]
        fields = {
            "request_id": context["request_id"],
            "requester_id": USER_ID,
            "chat_id": CHAT_ID,
            "status": "selecting_file",
            "expires_at": 2_000_000,
            "candidate_files_json": context["candidate_files_json"],
            "root_folder_token_snapshot": "root_demo",
            "folder_path_json": json.dumps(
                [
                    {
                        "token": "root_demo",
                        "name": "项目归档",
                        "url": "https://example/root",
                    }
                ],
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
        self.assertEqual(result["chat_id"], CHAT_ID)
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

    def test_prepare_choose_file_outputs_flat_base_fields(self):
        context = valid_request_context()
        candidate = json.loads(context["candidate_files_json"])[0]
        request = self._request_payload(context)["data"]["items"][0]["fields"]
        result = prepare_action(
            "choose_file",
            json.dumps(request, ensure_ascii=False),
            json.dumps(candidate, ensure_ascii=False),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["next_step"], "list_folder")
        self.assertEqual(result["status"], "selecting_folder")
        self.assertEqual(result["selected_file_key"], "file_key_demo")
        self.assertEqual(result["source_message_id"], FILE_MESSAGE_ID)
        self.assertEqual(
            result["current_folder_url_object"],
            {
                "text": "项目归档",
                "link": "https://example/root",
            },
        )

    def test_prepare_browse_and_back_keep_root_boundary(self):
        context = valid_request_context()
        request = self._request_payload(
            context,
            status="selecting_folder",
        )["data"]["items"][0]["fields"]
        folder = {
            "token": "folder_a",
            "name": "A",
            "url": "https://example/a",
            "parent_token": "root_demo",
        }
        browse = prepare_action(
            "browse",
            json.dumps(request, ensure_ascii=False),
            selected_folder_json=json.dumps(folder, ensure_ascii=False),
        )
        self.assertTrue(browse["ok"])
        self.assertEqual(browse["current_folder_token"], "folder_a")
        self.assertEqual(
            browse["current_folder_url_object"],
            {
                "text": "A",
                "link": "https://example/a",
            },
        )

        request["folder_path_json"] = browse["folder_path_json"]
        back = prepare_action(
            "back",
            json.dumps(request, ensure_ascii=False),
        )
        self.assertTrue(back["ok"])
        self.assertEqual(back["current_folder_token"], "root_demo")

        at_root = prepare_action(
            "back",
            json.dumps(request | {"folder_path_json": '[{"token":"root_demo","name":"项目归档"}]'}),
        )
        self.assertFalse(at_root["ok"])
        self.assertEqual(at_root["error_code"], "ALREADY_AT_ROOT")

    def test_prepare_current_folder_builds_target_url_object(self):
        context = valid_request_context()
        request = self._request_payload(
            context,
            status="selecting_folder",
        )["data"]["items"][0]["fields"]
        result = prepare_action(
            "choose_current_folder",
            json.dumps(request, ensure_ascii=False),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["next_step"], "send_confirm_card")
        self.assertEqual(
            result["target_folder_url_object"],
            {
                "text": "项目归档",
                "link": "https://example/root",
            },
        )

    def test_processing_request_validator_outputs_trusted_upload_fields(self):
        context = valid_request_context()
        payload = self._request_payload(
            context,
            status="processing",
            source_message_id=FILE_MESSAGE_ID,
            selected_file_key="file_key_demo",
            selected_file_name="项目终版.md",
            selected_file_type="md",
            target_folder_token="root_demo",
            target_folder_name="项目归档",
            target_folder_url={"text": "项目归档", "link": "https://example/root"},
        )
        result = validate_processing_request(payload, context["request_id"])

        self.assertTrue(result["ok"])
        self.assertTrue(result["should_upload"])
        self.assertEqual(result["chat_id_filter_values"], [CHAT_ID])
        self.assertEqual(result["target_folder_token"], "root_demo")
        self.assertEqual(result["target_folder_path"], "项目归档")

    def test_processing_request_validator_stops_terminal_request(self):
        context = valid_request_context()
        payload = self._request_payload(context, status="success")
        result = validate_processing_request(payload, context["request_id"])

        self.assertTrue(result["ok"])
        self.assertFalse(result["should_upload"])
        self.assertTrue(result["already_finished"])

    def test_upload_policy_uses_actual_size_and_current_mapping(self):
        result = validate_upload_policy(
            mapping_payload(),
            CHAT_ID,
            "md",
            1024,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["actual_size"], 1024)
        self.assertEqual(result["max_bytes"], 20 * 1024 * 1024)

    def test_upload_policy_rejects_empty_download(self):
        result = validate_upload_policy(
            mapping_payload(),
            CHAT_ID,
            "md",
            0,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "FILE_EMPTY")

    def test_download_size_counts_utf8_bytes(self):
        self.assertEqual(compute_actual_size("abc")["actual_size"], 3)
        self.assertEqual(compute_actual_size("中文")["actual_size"], 6)

    def test_download_size_passes_zero_through_for_b17_to_reject(self):
        result = compute_actual_size("")

        self.assertTrue(result["ok"])
        self.assertEqual(result["actual_size"], 0)

    def test_download_size_flags_missing_content(self):
        result = compute_actual_size(None)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "FILE_CONTENT_MISSING")

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
        result_from_path_json = build_result_card(
            "success",
            "archive_demo",
            USER_ID,
            "项目终版.md",
            "md",
            "A",
            '[{"name":"项目归档"},{"name":"A"}]',
            "https://example/a",
            "https://example/a/file",
            1024,
            2000,
        )
        self.assertEqual(
            result_from_path_json["target_folder_path"],
            "项目归档 / A",
        )
        self.assertEqual(result["result_size_text"], "1.0 MB")


class _FakeHttpResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class DownloadUploadNodeTests(unittest.TestCase):
    def test_missing_credentials_fail_before_network(self):
        result = download_and_upload("om_x", "file_key", "a.md", "fld_x")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "CREDENTIALS_MISSING")

    def test_download_upload_success_returns_token_url_and_size(self):
        content = b"%PDF-1.4 binary-bytes"
        responses = [
            _FakeHttpResponse(json.dumps({"tenant_access_token": "t-1"}).encode()),
            _FakeHttpResponse(content),
            _FakeHttpResponse(
                json.dumps({"code": 0, "data": {"file_token": "ft_1"}}).encode()
            ),
        ]
        with mock.patch(
            "aily_nodes.b9_download_and_upload.urlopen",
            side_effect=responses,
        ):
            result = download_and_upload(
                "om_x",
                "file_key",
                "a.pdf",
                "fld_x",
                app_id="id",
                app_secret="secret",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["file_token"], "ft_1")
        self.assertEqual(result["actual_size"], len(content))
        self.assertTrue(result["file_url"].endswith("ft_1"))

    def test_download_api_error_is_reported_as_download_failed(self):
        responses = [
            _FakeHttpResponse(json.dumps({"tenant_access_token": "t-1"}).encode()),
            _FakeHttpResponse(
                json.dumps({"code": 234008, "msg": "no permission"}).encode()
            ),
        ]
        with mock.patch(
            "aily_nodes.b9_download_and_upload.urlopen",
            side_effect=responses,
        ):
            result = download_and_upload(
                "om_x",
                "file_key",
                "a.pdf",
                "fld_x",
                app_id="id",
                app_secret="secret",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "DOWNLOAD_FAILED")
        self.assertIn("no permission", result["error"])

    def test_oversize_content_is_rejected_before_upload(self):
        big = b"a" * (20 * 1024 * 1024 + 1)
        responses = [
            _FakeHttpResponse(json.dumps({"tenant_access_token": "t-1"}).encode()),
            _FakeHttpResponse(big),
        ]
        with mock.patch(
            "aily_nodes.b9_download_and_upload.urlopen",
            side_effect=responses,
        ) as mocked:
            result = download_and_upload(
                "om_x",
                "file_key",
                "big.zip",
                "fld_x",
                app_id="id",
                app_secret="secret",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "FILE_TOO_LARGE")
        self.assertEqual(mocked.call_count, 2)


if __name__ == "__main__":
    unittest.main()
