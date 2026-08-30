from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.core.errors import ValidationError
from app.repositories.alert_repository import AlertRepository

VALID_OID = "65f1a2b3c4d5e6f7a8b9c0d1"


@pytest.fixture
def mock_collection(mocker):
    col = mocker.AsyncMock()
    col.find = mocker.MagicMock()
    return col


@pytest.fixture
def repo(mock_collection):
    return AlertRepository(mock_collection)


class TestOidValidation:
    def test_valid_oid_returns_object_id(self, repo):
        result = repo._oid(VALID_OID)
        assert isinstance(result, ObjectId)
        assert str(result) == VALID_OID

    def test_malformed_oid_raises_validation_error(self, repo):
        with pytest.raises(ValidationError, match="malformed id"):
            repo._oid("not-an-oid")


class TestCreate:
    async def test_inserts_and_returns_full_doc(self, repo, mock_collection, mocker):
        inserted_id = ObjectId(VALID_OID)
        mock_collection.insert_one.return_value = mocker.MagicMock(inserted_id=inserted_id)
        mock_collection.find_one.return_value = {"_id": inserted_id, "alert_id": "a1"}

        data = {"alert_id": "a1", "severity": "SEVERITY_WARNING"}
        result = await repo.create(data)

        mock_collection.insert_one.assert_awaited_once_with(data)
        mock_collection.find_one.assert_awaited_once_with({"_id": inserted_id})
        assert result["alert_id"] == "a1"


class TestGet:
    async def test_fetches_by_id(self, repo, mock_collection):
        expected = {"_id": ObjectId(VALID_OID), "alert_id": "a1"}
        mock_collection.find_one.return_value = expected

        result = await repo.get(VALID_OID)

        mock_collection.find_one.assert_awaited_once_with({"_id": ObjectId(VALID_OID)})
        assert result == expected

    async def test_returns_none_when_not_found(self, repo, mock_collection):
        mock_collection.find_one.return_value = None
        assert await repo.get(VALID_OID) is None

    async def test_malformed_id_raises_before_query(self, repo, mock_collection):
        with pytest.raises(ValidationError):
            await repo.get("bad-id")
        mock_collection.find_one.assert_not_called()


class TestList:
    async def test_default_query_no_sort(self, repo, mock_collection, mocker):
        cursor = mocker.MagicMock()
        cursor.skip.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = mocker.AsyncMock(return_value=[{"alert_id": "a1"}])
        mock_collection.find.return_value = cursor

        result = await repo.list()

        mock_collection.find.assert_called_once_with({})
        cursor.skip.assert_called_once_with(0)
        cursor.limit.assert_called_once_with(100)
        assert result == [{"alert_id": "a1"}]

    async def test_with_query_skip_limit_sort(self, repo, mock_collection, mocker):
        cursor = mocker.MagicMock()
        cursor.sort.return_value = cursor
        cursor.skip.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = mocker.AsyncMock(return_value=[])
        mock_collection.find.return_value = cursor

        await repo.list(
            query={"severity": "SEVERITY_WARNING"},
            limit=10,
            skip=5,
            sort=[("created_at", -1)],
        )

        mock_collection.find.assert_called_once_with({"severity": "SEVERITY_WARNING"})
        cursor.sort.assert_called_once_with([("created_at", -1)])
        cursor.skip.assert_called_once_with(5)
        cursor.limit.assert_called_once_with(10)


class TestUpdate:
    async def test_updates_and_returns_doc(self, repo, mock_collection):
        updated = {"_id": ObjectId(VALID_OID), "acknowledged": True}
        mock_collection.find_one_and_update.return_value = updated

        result = await repo.update(VALID_OID, {"acknowledged": True})

        mock_collection.find_one_and_update.assert_awaited_once()
        args, _ = mock_collection.find_one_and_update.call_args
        assert args[0] == {"_id": ObjectId(VALID_OID)}
        assert args[1] == {"$set": {"acknowledged": True}}
        assert result == updated

    async def test_returns_none_when_not_found(self, repo, mock_collection):
        mock_collection.find_one_and_update.return_value = None
        assert await repo.update(VALID_OID, {"x": 1}) is None


class TestDelete:
    async def test_returns_true_when_deleted(self, repo, mock_collection, mocker):
        mock_collection.delete_one.return_value = mocker.MagicMock(deleted_count=1)
        assert await repo.delete(VALID_OID) is True
        mock_collection.delete_one.assert_awaited_once_with({"_id": ObjectId(VALID_OID)})

    async def test_returns_false_when_not_found(self, repo, mock_collection, mocker):
        mock_collection.delete_one.return_value = mocker.MagicMock(deleted_count=0)
        assert await repo.delete(VALID_OID) is False


class TestCount:
    async def test_default_query(self, repo, mock_collection):
        mock_collection.count_documents.return_value = 7
        assert await repo.count() == 7
        mock_collection.count_documents.assert_awaited_once_with({})

    async def test_with_query(self, repo, mock_collection):
        mock_collection.count_documents.return_value = 3
        await repo.count({"severity": "SEVERITY_WARNING"})
        mock_collection.count_documents.assert_awaited_once_with({"severity": "SEVERITY_WARNING"})


class TestListPage:
    async def test_no_filters_sorts_by_created_at_and_id(self, repo, mock_collection, mocker):
        cursor = mocker.MagicMock()
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = mocker.AsyncMock(return_value=[])
        mock_collection.find.return_value = cursor
        await repo.list_page()
        mock_collection.find.assert_called_once_with({})
        cursor.sort.assert_called_once_with([("created_at", -1), ("_id", -1)])
        cursor.limit.assert_called_once_with(51)

    async def test_severity_and_acknowledged_narrow_the_query(self, repo, mock_collection, mocker):
        cursor = mocker.MagicMock()
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = mocker.AsyncMock(return_value=[])
        mock_collection.find.return_value = cursor
        await repo.list_page(severity="SEVERITY_WARNING", acknowledged=False, limit=11)
        mock_collection.find.assert_called_once_with(
            {"severity": "SEVERITY_WARNING", "acknowledged": False}
        )
        cursor.limit.assert_called_once_with(11)

    async def test_acknowledged_true_is_not_dropped_as_falsy(self, repo, mock_collection, mocker):
        cursor = mocker.MagicMock()
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = mocker.AsyncMock(return_value=[])
        mock_collection.find.return_value = cursor
        await repo.list_page(acknowledged=True)
        mock_collection.find.assert_called_once_with({"acknowledged": True})

    async def test_cursor_builds_tiebreak_or_clause(self, repo, mock_collection, mocker):
        cursor = mocker.MagicMock()
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = mocker.AsyncMock(return_value=[])
        mock_collection.find.return_value = cursor
        moment = datetime(2026, 8, 13, 12, 16, 26, 160000, tzinfo=UTC)
        await repo.list_page(after=(moment, VALID_OID))
        query = mock_collection.find.call_args[0][0]
        assert query["$and"] == [
            {
                "$or": [
                    {"created_at": {"$lt": moment}},
                    {"created_at": moment, "_id": {"$lt": ObjectId(VALID_OID)}},
                ]
            }
        ]

    async def test_malformed_cursor_id_rejected(self, repo, mock_collection):
        moment = datetime(2026, 8, 13, tzinfo=UTC)
        with pytest.raises(ValidationError):
            await repo.list_page(after=(moment, "not-an-oid"))


class TestAcknowledge:
    async def test_conditional_write_stamps_acknowledged_and_timestamp(
        self, repo, mock_collection, mocker
    ):
        mock_collection.update_one.return_value = mocker.MagicMock(matched_count=1)
        mock_collection.find_one.return_value = {"_id": ObjectId(VALID_OID), "acknowledged": True}
        await repo.acknowledge(VALID_OID)
        mock_collection.update_one.assert_awaited_once()
        filter_, update = mock_collection.update_one.await_args.args
        assert filter_["_id"] == ObjectId(VALID_OID)
        assert filter_["acknowledged"] == {"$ne": True}
        changes = update["$set"]
        assert changes["acknowledged"] is True
        assert isinstance(changes["acknowledged_at"], datetime)
        assert changes["acknowledged_at"].tzinfo == UTC

    async def test_first_acknowledge_reports_flipped(self, repo, mock_collection, mocker):
        mock_collection.update_one.return_value = mocker.MagicMock(matched_count=1)
        mock_collection.find_one.return_value = {"_id": ObjectId(VALID_OID), "acknowledged": True}
        doc, flipped = await repo.acknowledge(VALID_OID)
        assert doc is not None
        assert flipped is True

    async def test_repeat_acknowledge_reports_not_flipped(self, repo, mock_collection, mocker):
        mock_collection.update_one.return_value = mocker.MagicMock(matched_count=0)
        mock_collection.find_one.return_value = {"_id": ObjectId(VALID_OID), "acknowledged": True}
        doc, flipped = await repo.acknowledge(VALID_OID)
        assert doc is not None
        assert flipped is False
