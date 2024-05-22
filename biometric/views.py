from datetime import datetime
import json
import pytz
import requests
from threading import Thread
from urllib.parse import parse_qs
from urllib.parse import unquote
from django.shortcuts import render, redirect
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext as __
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from apscheduler.schedulers.background import BackgroundScheduler
from biometric.filters import BiometricDeviceFilter
from Mibs.filters import MibsPaginator
from Mibs import settings
from zk import ZK
from attendance.views.clock_in_out import clock_in, clock_out
from base.methods import get_key_instances, get_pagination
from employee.models import Employee, EmployeeWorkInformation
from Mibs.decorators import (
    install_required,
    permission_required,
    login_required,
)
from base.methods import get_key_instances
from .forms import (
    BiometricDeviceForm,
    BiometricDeviceSchedulerForm,
    EmployeeBiometricAddForm,
)

from .models import (
    BiometricDevices,
    BiometricEmployees,
)


def str_time_seconds(time):
    """
    this method is used reconvert time in H:M formate string back to seconds and return it
    args:
        time : time in H:M format
    """

    ftr = [3600, 60, 1]
    return sum(a * b for a, b in zip(ftr, map(int, time.split(":"))))


def paginator_qry(qryset, page_number):
    """
    This method is used to paginate query set
    """
    paginator = MibsPaginator(qryset, get_pagination())
    qryset = paginator.get_page(page_number)
    return qryset


def biometric_set_time(conn):
    """
    Sets the time on the biometric device using the provided connection.

    Parameters:
    - conn: The connection to the biometric device.

    Returns:
    None
    """
    new_time = datetime.today()
    conn.set_time(new_time)


class Request:
    """
    Represents a request for clock-in or clock-out.

    Attributes:
    - user: The user associated with the request.
    - date: The date of the request.
    - time: The time of the request.
    - path: The path associated with the request (default: "/").
    - session: The session data associated with the request (default: {"title": None}).
    """

    def __init__(
        self,
        user,
        date,
        time,
        datetime,
    ) -> None:
        self.user = user
        self.path = "/"
        self.session = {"title": None}
        self.date = date
        self.time = time
        self.datetime = datetime


class ZKBioAttendance(Thread):
    """
    Represents a thread for capturing live attendance data from a ZKTeco biometric device.

    Attributes:
    - machine_ip: The IP address of the ZKTeco biometric device.
    - port_no: The port number for communication with the ZKTeco biometric device.
    - conn: The connection object to the ZKTeco biometric device.

    Methods:
    - run(): Overrides the run method of the Thread class to capture live attendance data.
    """

    def __init__(self, machine_ip, port_no):
        self.machine_ip = machine_ip
        self.port_no = port_no
        zk_device = ZK(
            machine_ip,
            port=port_no,
            timeout=5,
            password=0,
            force_udp=False,
            ommit_ping=False,
        )
        conn = zk_device.connect()
        self.conn = conn
        Thread.__init__(self)

    def run(self):
        try:
            device = BiometricDevices.objects.filter(
                machine_ip=self.machine_ip, port=self.port_no
            ).first()
            if device.is_live:
                attendances = self.conn.live_capture()
                for attendance in attendances:
                    if attendance:
                        user_id = attendance.user_id
                        punch_code = attendance.punch
                        date_time = attendance.timestamp
                        date = date_time.date()
                        time = date_time.time()
                        if device:
                            device.last_fetch_date = date
                            device.last_fetch_time = time
                            device.save()
                        bio_id = BiometricEmployees.objects.filter(
                            user_id=user_id
                        ).first()
                        if bio_id:
                            if punch_code in {0, 3, 4}:
                                try:
                                    clock_in(
                                        Request(
                                            user=bio_id.employee_id.employee_user_id,
                                            date=date,
                                            time=time,
                                            datetime=date_time,
                                        )
                                    )
                                except Exception as error:
                                    print(f"Got an error in clock_in {error}")
                                    continue
                            else:
                                try:
                                    clock_out(
                                        Request(
                                            user=bio_id.employee_id.employee_user_id,
                                            date=date,
                                            time=time,
                                            datetime=date_time,
                                        )
                                    )
                                except Exception as error:
                                    print(f"Got an error in clock_out {error}")
                                    continue
                    else:
                        continue
        except ConnectionResetError as error:
            ZKBioAttendance(self.machine_ip, self.port_no).start()


class AnvizBiometricDeviceManager:
    """Manages communication with Anviz biometric devices for attendance records."""

    def __init__(self, device_id):
        """
        Initializes the AnvizBiometricDeviceManager.

        :param device_id: The Object ID of the biometric device.
        """
        self.device = BiometricDevices.objects.get(id=device_id)
        self.begin_time = None
        self.end_time = None

    def get_attendance_payload(self):
        """
        Constructs the payload for retrieving attendance records.

        :return: A dictionary containing the payload.
        """
        current_utc_time = datetime.utcnow()
        self.begin_time = (
            datetime.combine(self.device.last_fetch_date, self.device.last_fetch_time)
            if self.device.last_fetch_date and self.device.last_fetch_time
            else current_utc_time.replace(hour=0, minute=0, second=0, microsecond=0)
        )
        self.end_time = current_utc_time
        begin_time_str = self.begin_time.isoformat() + "+00:00"
        end_time_str = self.end_time.isoformat() + "+00:00"
        return {
            "header": {
                "nameSpace": "attendance.record",
                "nameAction": "getrecord",
                "version": "1.0",
                "requestId": "f1becc28-ad01-b5b2-7cef-392eb1526f39",
                "timestamp": "2022-10-21T07:39:07+00:00",
            },
            "authorize": {
                "type": "token",
                "token": self.device.api_token,
            },
            "payload": {
                "begin_time": begin_time_str,
                "end_time": end_time_str,
                "order": "asc",
                "page": "1",
                "per_page": "100",
            },
        }

    def refresh_api_token(self):
        """
        Refreshes the API token for the device.

        This method sends a request to the API to refresh the token.
        """
        token_payload = {
            "header": {
                "nameSpace": "authorize.token",
                "nameAction": "token",
                "version": "1.0",
                "requestId": "f1becc28-ad01-b5b2-7cef-392eb1526f39",
                "timestamp": "2022-10-21T07:39:07+00:00",
            },
            "payload": {
                "api_key": self.device.api_key,
                "api_secret": self.device.api_secret,
            },
        }
        response = requests.post(self.device.api_url, json=token_payload, timeout=30)
        api_response = response.json()
        token = api_response["payload"]["token"]
        expires = api_response["payload"]["expires"]
        self.device.api_token = token
        self.device.api_expires = expires
        self.device.save()

    def get_attendance_records(self):
        """
        Retrieves attendance records from the biometric device.

        :return: A dictionary containing the attendance records.
        """
        token_expire = {
            "header": {"nameSpace": "System", "name": "Exception"},
            "payload": {"type": "TOKEN_EXPIRES", "message": "TOKEN_EXPIRES"},
        }
        attendance_payload = self.get_attendance_payload()
        response = requests.post(
            self.device.api_url, json=attendance_payload, timeout=30
        )
        api_response = response.json()
        if api_response == token_expire:
            self.refresh_api_token()
            attendance_payload = self.get_attendance_payload()
            response = requests.post(
                self.device.api_url, json=attendance_payload, timeout=30
            )
            api_response = response.json()
        page_count = response.json()["payload"]["pageCount"]
        if page_count > 1:
            page = attendance_payload["payload"]["page"]
            for page in range(2, page_count + 1):
                attendance_payload["payload"]["page"] = str(page)
                response = requests.post(
                    self.device.api_url, json=attendance_payload, timeout=30
                )
                if response.json() == token_expire:
                    self.refresh_api_token()
                    attendance_payload = self.get_attendance_payload()
                    response = requests.post(
                        self.device.api_url, json=attendance_payload, timeout=30
                    )
                page_records = response.json().get("payload", {}).get("list", [])
                api_response["payload"]["list"].extend(page_records)
        self.device.last_fetch_date, self.device.last_fetch_time = (
            self.end_time.date(),
            self.end_time.time(),
        )
        self.device.save()
        return api_response


def anviz_biometric_device_attendance(device_id):
    """
    Retrieves attendance records from an Anviz biometric device and processes them.

    :param device_id: The Object Id of the Anviz biometric device.
    """
    anviz_device = AnvizBiometricDeviceManager(device_id)
    attendance_records = anviz_device.get_attendance_records()
    for attendance in attendance_records["payload"]["list"]:
        badge_id = attendance["employee"]["workno"]
        punch_code = attendance["checktype"]
        date_time_obj = datetime.strptime(
            attendance["checktime"], "%Y-%m-%dT%H:%M:%S%z"
        )
        target_timezone = pytz.timezone(settings.TIME_ZONE)

        date_time_obj = date_time_obj.astimezone(target_timezone)
        employee = Employee.objects.filter(badge_id=badge_id).first()
        if employee:
            if punch_code in {0, 128}:
                try:
                    clock_in(
                        Request(
                            user=employee.employee_user_id,
                            date=date_time_obj.date(),
                            time=date_time_obj.time(),
                            datetime=date_time_obj,
                        )
                    )
                except Exception as error:
                    print(f"Error in clock in {error}")

            else:
                try:
                    # // 1 , 129 checktype check out and door close
                    clock_out(
                        Request(
                            user=employee.employee_user_id,
                            date=date_time_obj.date(),
                            time=date_time_obj.time(),
                            datetime=date_time_obj,
                        )
                    )
                except Exception as error:
                    print(f"Error in clock out {error}")


@login_required
@install_required
@permission_required("attendance.view_biometricdevices")
def biometric_devices_view(request):
    biometric_form = BiometricDeviceForm()
    filter_form = BiometricDeviceFilter()
    biometric_devices = BiometricDevices.objects.filter(is_active=True).order_by(
        "-created_at"
    )
    biometric_devices = paginator_qry(biometric_devices, request.GET.get("page"))
    template = "biometric/view_biometric_devices.html"
    context = {
        "biometric_form": biometric_form,
        "devices": biometric_devices,
        "f": filter_form,
    }
    return render(request, template, context)


@login_required
@install_required
@permission_required("attendance.add_biometricdevices")
def biometric_device_schedule(request, device_id):
    device = BiometricDevices.objects.get(id=device_id)
    initial_data = {"scheduler_duration": device.scheduler_duration}
    scheduler_form = BiometricDeviceSchedulerForm(initial=initial_data)
    context = {
        "scheduler_form": scheduler_form,
        "device_id": device_id,
    }
    if request.method == "POST":
        scheduler_form = BiometricDeviceSchedulerForm(request.POST)
        if scheduler_form.is_valid():
            if device.machine_type == "zk":
                try:
                    port_no = device.port
                    machine_ip = device.machine_ip
                    conn = None
                    zk = ZK(
                        machine_ip,
                        port=port_no,
                        timeout=5,
                        password=0,
                        force_udp=False,
                        ommit_ping=False,
                    )
                    conn = zk.connect()
                    conn.test_voice(index=0)
                    duration = request.POST.get("scheduler_duration")
                    device = BiometricDevices.objects.get(id=device_id)
                    device.scheduler_duration = duration
                    device.is_scheduler = True
                    device.is_live = False
                    device.save()
                    scheduler = BackgroundScheduler()
                    scheduler.add_job(
                        lambda: zk_biometric_device_attendance(device.id),
                        "interval",
                        seconds=str_time_seconds(device.scheduler_duration),
                    )
                    scheduler.start()
                    return HttpResponse("<script>window.location.reload()</script>")
                except Exception as e:
                    print(f"An error comes in biometric_device_schedule {e}")
                    script = """
                    <script>
                        Swal.fire({
                          title : "Schedule Attendance unsuccessful",
                          text: "Please double-check the accuracy of the provided IP Address and Port Number for correctness",
                          icon: "warning",
                          showConfirmButton: false,
                          timer: 3500, 
                          timerProgressBar: true,
                          didClose: () => {
                            location.reload(); 
                            },
                        });
                    </script>
                    """
                    return HttpResponse(script)
            else:
                duration = request.POST.get("scheduler_duration")
                device.is_scheduler = True
                device.scheduler_duration = duration
                device.save()
                scheduler = BackgroundScheduler()
                scheduler.add_job(
                    lambda: anviz_biometric_device_attendance(device.id),
                    "interval",
                    seconds=str_time_seconds(device.scheduler_duration),
                )
                scheduler.start()
                return HttpResponse("<script>window.location.reload()</script>")

        context["scheduler_form"] = scheduler_form
        response = render(request, "biometric/scheduler_device_form.html", context)
        return HttpResponse(
            response.content.decode("utf-8")
            + "<script>$('#BiometricDeviceTestModal').removeClass('oh-modal--show');$('#BiometricDeviceModal').toggleClass('oh-modal--show');</script>"
        )
    return render(request, "biometric/scheduler_device_form.html", context)


def biometric_device_unschedule(request, device_id):
    device = BiometricDevices.objects.get(id=device_id)
    device.is_scheduler = False
    device.save()
    return redirect(biometric_devices_view)


@login_required
@install_required
@permission_required("attendance.add_biometricdevices")
def biometric_device_add(request):
    previous_data = unquote(request.GET.urlencode())[len("pd=") :]
    biometric_form = BiometricDeviceForm()
    if request.method == "POST":
        biometric_form = BiometricDeviceForm(request.POST)
        if biometric_form.is_valid():
            biometric_form.save()
            messages.success(request, _("Biometric device added successfully."))
            biometric_form = BiometricDeviceForm()
    context = {"biometric_form": biometric_form, "pd": previous_data}
    return render(request, "biometric/add_biometric_device.html", context)


@login_required
@install_required
@permission_required("attendance.change_biometricdevices")
def biometric_device_edit(request, device_id):
    device = BiometricDevices.objects.get(id=device_id)
    biometric_form = BiometricDeviceForm(instance=device)
    if request.method == "POST":
        biometric_form = BiometricDeviceForm(request.POST, instance=device)
        if biometric_form.is_valid():
            biometric_form.save()
            messages.success(request, _("Biometric device updated successfully."))
    context = {
        "biometric_form": biometric_form,
        "device_id": device_id,
    }
    return render(request, "biometric/edit_biometric_device.html", context)


@login_required
@install_required
@permission_required(perm="attendance.delete_biometricdevices")
def biometric_device_archive(request, device_id):
    """
    This method is used to archive or un-archive devices
    """
    pd = request.GET.urlencode()
    device_obj = BiometricDevices.objects.get(id=device_id)
    device_obj.is_active = not device_obj.is_active
    device_obj.save()
    message = _("archived") if not device_obj.is_active else _("un-archived")
    messages.success(request, _("Device is %(message)s") % {"message": message})
    return redirect(f"/biometric/search-devices?{pd}")


@login_required
@install_required
@permission_required(perm="attendance.delete_biometricdevices")
def biometric_device_delete(request, device_id):
    device = BiometricDevices.objects.get(id=device_id)
    device.delete()
    pd = request.GET.urlencode()
    if not BiometricDevices.objects.filter(machine_type="zk"):
        BiometricEmployees.objects.all().delete()
    messages.success(request, _("Biometric device deleted successfully."))
    return redirect(f"/biometric/search-devices?{pd}")


@login_required
@install_required
@permission_required("attendance.view_biometricdevices")
def search_devices(request):
    """
    This method is used to search biometric device model and return matching objects
    """
    previous_data = request.GET.urlencode()
    search = request.GET.get("search")
    is_active = request.GET.get("is_active")
    if search is None:
        search = ""
    devices = BiometricDeviceFilter(request.GET).qs.order_by("-created_at")
    if not is_active or is_active == "unknown":
        devices = devices.filter(is_active=True)
    data_dict = []
    data_dict = parse_qs(previous_data)
    get_key_instances(BiometricDevices, data_dict)
    template = "biometric/card_biometric_devices.html"
    if request.GET.get("view") == "list":
        template = "biometric/list_biometric_devices.html"

    devices = paginator_qry(devices, request.GET.get("page"))
    return render(
        request,
        template,
        {
            "devices": devices,
            "pd": previous_data,
            "filter_dict": data_dict,
        },
    )


@login_required
@install_required
@permission_required("attendance.add_biometricdevices")
def biometric_device_test(request, device_id):
    device = BiometricDevices.objects.get(id=device_id)
    if device.machine_type == "zk":
        port_no = device.port
        machine_ip = device.machine_ip
        conn = None
        # create ZK instance
        zk = ZK(
            machine_ip,
            port=port_no,
            timeout=5,
            password=0,
            force_udp=False,
            ommit_ping=False,
        )
        try:
            conn = zk.connect()
            conn.test_voice(index=0)
            biometric_set_time(conn)
            script = """<script>
                    Swal.fire({
                      text: "Connection test successful.",
                      icon: "success",
                      showConfirmButton: false,
                      timer: 1500,
                      timerProgressBar: true,
                      didClose: () => {
                        location.reload();
                        },
                    });
                    </script>
                """
        except Exception as e:
            print(f"An error comes in biometric_device_test {e}")
            script = """
           <script>
                Swal.fire({
                  title : "Connection unsuccessful",
                  text: "Please double-check the accuracy of the provided IP Address and Port Number for correctness",
                  icon: "warning",
                  showConfirmButton: false,
                  timer: 3500, 
                  timerProgressBar: true,
                  didClose: () => {
                    location.reload(); 
                    },
                });
            </script>
            """
        finally:
            if conn:
                conn.disconnect()
    else:
        payload = {
            "header": {
                "nameSpace": "authorize.token",
                "nameAction": "token",
                "version": "1.0",
                "requestId": "f1becc28-ad01-b5b2-7cef-392eb1526f39",
                "timestamp": "2022-10-21T07:39:07+00:00",
            },
            "payload": {"api_key": device.api_key, "api_secret": device.api_secret},
        }
        error = {
            "header": {"nameSpace": "System", "name": "Exception"},
            "payload": {"type": "AUTH_ERROR", "message": "AUTH_ERROR"},
        }
        script = """
           <script>
                Swal.fire({
                  title : "Connection unsuccessful",
                  text: "Pleaseq double-check the accuracy of the provided API Url , API Key and API Secret for correctness",
                  icon: "warning",
                  showConfirmButton: false,
                  timer: 3500, 
                  timerProgressBar: true,
                  didClose: () => {
                    location.reload(); 
                    },
                });
            </script>
            """
        try:
            response = requests.post(
                device.api_url,
                json=payload,
            )
            if response.status_code != 200:
                pass
            api_response = response.json()
            if api_response == error:
                pass
            else:
                payload = api_response["payload"]
                api_token = payload["token"]
                api_expires = payload["expires"]
                device.api_token = api_token
                device.api_expires = api_expires
                device.save()
                anviz_device = AnvizBiometricDeviceManager(device_id)
                attendance_records = anviz_device.get_attendance_records()
                script = """<script>
                    Swal.fire({
                      text: "Test connection successful.",
                      icon: "success",
                      showConfirmButton: false,
                      timer: 1500,
                      timerProgressBar: true,
                      didClose: () => {
                        location.reload();
                        },
                    });
                    </script>
                """
        except Exception as e:
            pass

    return HttpResponse(script)


def employees_fetch(device):
    zk = ZK(
        device.machine_ip,
        port=device.port,
        timeout=1,
        password=0,
        force_udp=False,
        ommit_ping=False,
    )
    conn = zk.connect()
    conn.enable_device()
    users = conn.get_users()
    fingers = conn.get_templates()
    employees = []
    for user in users:
        user_id = user.user_id
        uid = user.uid
        bio_id = BiometricEmployees.objects.filter(user_id=user_id).first()
        if bio_id:
            employee = bio_id.employee_id
            employee_work_info = EmployeeWorkInformation.objects.filter(
                employee_id=employee
            ).first()
            if employee_work_info:
                work_email = (
                    employee_work_info.email if employee_work_info.email else None
                )
                phone = employee_work_info.mobile if employee_work_info.mobile else None
                job_position = (
                    employee_work_info.job_position_id
                    if employee_work_info.job_position_id
                    else None
                )
                user.__dict__["work_email"] = work_email
                user.__dict__["phone"] = phone
                user.__dict__["job_position"] = job_position
            else:
                user.__dict__["work_email"] = None
                user.__dict__["phone"] = None
                user.__dict__["job_position"] = None
            user.__dict__["employee"] = employee
            user.__dict__["badge_id"] = employee.badge_id
            finger_print = []
            for finger in fingers:
                if finger.uid == uid:
                    finger_print.append(finger.fid)
            if not finger_print:
                finger_print = []
            user.__dict__["finger"] = finger_print
            employees.append(user)
    return employees


@login_required
@install_required
@permission_required("attendance.view_biometricdevices")
def biometric_device_employees(request, device_id, **kwargs):
    previous_data = request.GET.urlencode()
    employee_add_form = EmployeeBiometricAddForm()
    device = BiometricDevices.objects.get(id=device_id)
    try:
        employees = employees_fetch(device)
        
        employees = paginator_qry(employees, request.GET.get("page"))
        context = {
            "employees": employees,
            "device_id": device_id,
            "form": employee_add_form,
            "pd": previous_data,
        }
        return render(request, "biometric/view_employees_biometric.html", context)
    except Exception as e:
        print(f"An error occurred: {e}")
        messages.info(
            request,
            _(
                "Failed to establish a connection. Please verify the accuracy of the IP Address and Port No. of the device."
            ),
        )
        return redirect(biometric_devices_view)


@login_required
@install_required
@permission_required("attendance.view_biometricdevices")
def search_employee_device(request):
    previous_data = request.GET.urlencode()
    device_id = request.GET.get("device")
    device = BiometricDevices.objects.get(id=device_id)
    search = request.GET.get("search")
    employees = employees_fetch(device)
    if search:
        search_employees = BiometricEmployees.objects.filter(
            employee_id__employee_first_name__icontains=search
        )
        search_uids = search_employees.values_list("uid", flat=True)
        employees = [employee for employee in employees if employee.uid in search_uids]
    employees = paginator_qry(employees, request.GET.get("page"))
    template = "biometric/list_employees_biometric.html"
    context = {
        "employees": employees,
        "device_id": device_id,
        "pd": previous_data,
    }
    return render(request, template, context)


@login_required
@install_required
@permission_required("attendance.delete_biometricdevices")
def delete_biometric_user(request, uid, device_id):
    device = BiometricDevices.objects.get(id=device_id)
    zk = ZK(
        device.machine_ip,
        port=device.port,
        timeout=5,
        password=0,
        force_udp=False,
        ommit_ping=False,
    )
    conn = zk.connect()
    conn.delete_user(uid=uid)
    employee_bio = BiometricEmployees.objects.filter(uid=uid).first()
    employee_bio.delete()
    messages.success(
        request,
        _(
            "{} successfully removed from the biometric device.".format(
                employee_bio.employee_id
            ),
        ),
    )
    redirect_url = f"/biometric/biometric-device-employees/{device_id}/"
    return redirect(redirect_url)


@login_required
@install_required
@permission_required("attendance.delete_biometricdevices")
def bio_users_bulk_delete(request):
    conn = None
    json_ids = request.POST["ids"]
    device_id = request.POST["deviceId"]
    ids = json.loads(json_ids)
    device = BiometricDevices.objects.get(id=device_id)
    try:
        zk = ZK(
            device.machine_ip,
            port=device.port,
            timeout=5,
            password=0,
            force_udp=False,
            ommit_ping=False,
        )
        conn = zk.connect()
        for id in ids:
            user_id = int(id)
            conn.delete_user(user_id=user_id)
            employee_bio = BiometricEmployees.objects.filter(user_id=user_id).first()
            employee_bio.delete()
            conn.refresh_data()
            messages.success(
                request,
                _(
                    "{} successfully removed from the biometric device.".format(
                        employee_bio.employee_id
                    ),
                ),
            )
    except Exception as e:
        print(f"An error occurred: {e}")
    return JsonResponse({"messages": "Success"})


def add_biometric_user(request, device_id):
    if request.method == "POST":
        device = BiometricDevices.objects.get(id=device_id)
        try:
            zk = ZK(
                device.machine_ip,
                port=device.port,
                timeout=5,
                password=0,
                force_udp=False,
                ommit_ping=False,
            )
            conn = zk.connect()
            conn.enable_device()
            existing_uids = [user.uid for user in conn.get_users()]
            existing_user_ids = [user.user_id for user in conn.get_users()]
            existing_user_ids = [user.user_id for user in conn.get_users()]
            uid = 1
            user_id = 1000
            employee_ids = request.POST.getlist("employee_ids")
            for id in employee_ids:
                employee = Employee.objects.get(id=id)
                while uid in existing_uids or user_id in existing_user_ids:
                    user_id = int(user_id)
                    uid += 1
                    user_id += 1
                existing_uids.append(uid)
                existing_user_ids.append(user_id)
                existing_biometric_employee = BiometricEmployees.objects.filter(
                    employee_id=employee
                ).first()
                if existing_biometric_employee is None:
                    user_id = str(user_id)
                    conn.set_user(
                        uid=uid,
                        name=employee.employee_first_name
                        + " "
                        + employee.employee_last_name,
                        password="",
                        group_id="",
                        user_id=user_id,
                        card=0,
                    )
                    employee_bio = BiometricEmployees.objects.create(
                        uid=uid, user_id=user_id, employee_id=employee
                    )
                    messages.success(
                        request,
                        _(
                            "{} added to biometric device successfully".format(
                                employee
                            ),
                        ),
                    )
                else:
                    messages.info(
                        request,
                        _(
                            "{} already added to biometric device".format(employee),
                        ),
                    )

        except Exception as e:
            conn.disable_device()
            print(f"An error occurred: {str(e)}")

    return HttpResponse("<script>window.location.reload()</script>")


def biometric_device_live(request):
    """
    Activate or deactivate live capture mode for a biometric device based on the request parameters.

    :param request: The Django request object.
    :return: A JsonResponse containing a script to be executed on the client side.
    """
    is_live = request.GET.get("is_live")
    device_id = request.GET.get("deviceId")
    device = BiometricDevices.objects.get(id=device_id)
    is_live = True if is_live == "true" else False
    if is_live:
        port_no = device.port
        machine_ip = device.machine_ip
        conn = None
        # create ZK instance
        zk_device = ZK(
            machine_ip,
            port=port_no,
            timeout=5,
            password=0,
            force_udp=False,
            ommit_ping=False,
        )
        try:
            conn = zk_device.connect()
            instance = ZKBioAttendance(machine_ip, port_no)
            conn.test_voice(index=14)
            if conn:
                device.is_live = True
                device.is_scheduler = False
                device.save()
                instance.start()
            script = """<script>
                    Swal.fire({
                      text: "The live capture mode has been activated successfully.",
                      icon: "success",
                      showConfirmButton: false,
                      timer: 1500,
                      timerProgressBar: true, // Show a progress bar as the timer counts down
                      didClose: () => {
                        location.reload(); // Reload the page after the SweetAlert is closed
                        },
                    });
                    </script>
                """
        except Exception as error:
            device.is_live = False
            device.save()
            print(f"An error comes in biometric_device_live {error}")
            script = """
           <script>
                Swal.fire({
                  title : "Connection unsuccessful",
                  text: "Please double-check the accuracy of the provided IP Address and Port Number for correctness",
                  icon: "warning",
                  showConfirmButton: false,
                  timer: 3000,
                  timerProgressBar: true,
                  didClose: () => {
                    location.reload();
                    },
                });
            </script>
            """
        finally:
            if conn:
                conn.disconnect()
    else:
        device.is_live = False
        device.save()
        script = """
           <script>
                Swal.fire({
                  text: "The live capture mode has been deactivated successfully.",
                  icon: "warning",
                  showConfirmButton: false,
                  timer: 3000,
                  timerProgressBar: true,
                  didClose: () => {
                    location.reload();
                    },
                });
            </script>
            """
    return JsonResponse({"script": script})


def zk_biometric_device_attendance(device_id):
    """
    Retrieve attendance records from a ZK biometric device and update the clock-in/clock-out status.

    :param device_id: The ID of the ZK biometric device.
    """
    device = BiometricDevices.objects.get(id=device_id)
    if device.is_scheduler:
        port_no = device.port
        machine_ip = device.machine_ip
        conn = None
        zk_device = ZK(
            machine_ip,
            port=port_no,
            timeout=5,
            password=0,
            force_udp=False,
            ommit_ping=False,
        )
        try:
            conn = zk_device.connect()
            conn.enable_device()
            attendances = conn.get_attendance()
            last_attendance_datetime = attendances[-1].timestamp
            if device.last_fetch_date and device.last_fetch_time:
                filtered_attendances = [
                    attendance
                    for attendance in attendances
                    if attendance.timestamp.date() >= device.last_fetch_date
                    and attendance.timestamp.time() > device.last_fetch_time
                ]
            else:
                filtered_attendances = attendances
            device.last_fetch_date = last_attendance_datetime.date()
            device.last_fetch_time = last_attendance_datetime.time()
            device.save()
            for attendance in filtered_attendances:
                user_id = attendance.user_id
                punch_code = attendance.punch
                date_time = attendance.timestamp
                date = date_time.date()
                time = date_time.time()
                bio_id = BiometricEmployees.objects.filter(user_id=user_id).first()
                if bio_id:
                    if punch_code in {0, 3, 4}:
                        try:
                            clock_in(
                                Request(
                                    user=bio_id.employee_id.employee_user_id,
                                    date=date,
                                    time=time,
                                    datetime=date_time,
                                )
                            )
                        except Exception as error:
                            print(f"Got an error : {error}")
                    else:
                        try:
                            clock_out(
                                Request(
                                    user=bio_id.employee_id.employee_user_id,
                                    date=date,
                                    time=time,
                                    datetime=date_time,
                                )
                            )
                        except Exception as error:
                            print(f"Got an error : {error}")
        except Exception as error:
            print(f"Process terminate : {error}")
        finally:
            if conn:
                conn.disconnect()


try:
    devices = BiometricDevices.objects.all().update(is_live=False)
    for device in BiometricDevices.objects.filter(is_scheduler=True):
        if device:
            if str_time_seconds(device.scheduler_duration) > 0:
                if device.machine_type == "anviz":
                    scheduler = BackgroundScheduler()
                    scheduler.add_job(
                        lambda: anviz_biometric_device_attendance(device.id),
                        "interval",
                        seconds=str_time_seconds(device.scheduler_duration),
                    )
                    scheduler.start()
                elif device.machine_type == "zk":
                    scheduler = BackgroundScheduler()
                    scheduler.add_job(
                        lambda: zk_biometric_device_attendance(device.id),
                        "interval",
                        seconds=str_time_seconds(device.scheduler_duration),
                    )
                    scheduler.start()
                else:
                    pass
except:
    pass
