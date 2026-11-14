# Based on containerd v2.3.7 contrib/apparmor/template.go (Apache-2.0).
# Keep the default restrictions; allow only the exact stacked container peer
# that Ubuntu 26.04 adds when apparmor_restrict_unprivileged_unconfined=1.
abi <abi/3.0>,
#include <tunables/global>

profile cri-containerd.apparmor.d flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  network,
  capability,
  file,
  umount,
  # Host and K3s manager processes may signal container processes.
  signal (receive) peer=unconfined,
  signal (receive) peer=runc,
  signal (receive) peer=crun,
  # Preserve same-container signals for both ordinary and Ubuntu stacked labels.
  signal (send,receive) peer=cri-containerd.apparmor.d,
  signal (send,receive) peer=cri-containerd.apparmor.d//&unconfined,
  deny @{PROC}/* w,
  deny @{PROC}/{[^1-9/],[^1-9/][^0-9/],[^1-9s/][^0-9y/][^0-9s/],[^1-9/][^0-9/][^0-9/][^0-9/]*}/** w,
  deny @{PROC}/sys/[^k]** w,
  deny @{PROC}/sys/kernel/{?,??,[^s][^h][^m]**} w,
  deny @{PROC}/sysrq-trigger rwklx,
  deny @{PROC}/kcore rwklx,
  deny mount,
  deny /sys/[^f]*/** wklx,
  deny /sys/f[^s]*/** wklx,
  deny /sys/fs/[^c]*/** wklx,
  deny /sys/fs/c[^g]*/** wklx,
  deny /sys/fs/cg[^r]*/** wklx,
  deny /sys/firmware/** rwklx,
  deny /sys/devices/virtual/powercap/** rwklx,
  deny /sys/kernel/security/** rwklx,
  # Keep ptrace permissions scoped to peers in this exact container profile.
  ptrace (trace,tracedby,read,readby) peer=cri-containerd.apparmor.d,
  ptrace (trace,tracedby,read,readby) peer=cri-containerd.apparmor.d//&unconfined,
}
