from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from service.request_slots import request_slot


def test_local_processes_cannot_admit_more_than_two_requests_and_failure_releases_lock(tmp_path):
    entered=[Event(),Event()];release=Event()
    def occupy(index):
        with request_slot('https://model.example',2,1,tmp_path):
            entered[index].set();release.wait(2)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures=[workers.submit(occupy,index) for index in range(2)]
        assert all(event.wait(1) for event in entered)
        with pytest.raises(TimeoutError):
            with request_slot('https://model.example',2,.05,tmp_path):pass
        release.set()
        for future in futures:future.result()
    with pytest.raises(ValueError):
        with request_slot('https://model.example',2,.1,tmp_path):raise ValueError('cancelled operation')
    with request_slot('https://model.example',1,.1,tmp_path):pass
