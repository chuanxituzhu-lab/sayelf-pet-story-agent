import unittest

from pet_fde.providers.base import VideoGenerationRequest, VideoProviderAdapter
from pet_fde.providers.fault import FaultVideoProvider
from pet_fde.providers.mock import MockVideoProvider


def assert_provider_contract(test: unittest.TestCase, provider: VideoProviderAdapter, expected_success: bool) -> None:
    result = provider.generate(VideoGenerationRequest("j1", ("shot-1",), "9:16"))
    test.assertIsInstance(result.success, bool)
    test.assertEqual(result.success, expected_success)
    test.assertTrue(result.provider_name)
    if expected_success:
        test.assertTrue(result.provider_ref)
        test.assertTrue(result.local_path)
    else:
        test.assertTrue(result.error_code)


class ProviderContractTests(unittest.TestCase):
    def test_mock_provider_contract(self) -> None:
        assert_provider_contract(self, MockVideoProvider(), True)

    def test_fault_provider_contract_and_recovery(self) -> None:
        provider = FaultVideoProvider(MockVideoProvider(), failures=1)
        assert_provider_contract(self, provider, False)
        assert_provider_contract(self, provider, True)
