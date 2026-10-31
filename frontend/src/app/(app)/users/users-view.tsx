"use client";

import { LoaderCircle, ShieldOff, UserPlus, UsersRound } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { StateMessage } from "@/components/data-table";
import { EmptyState } from "@/components/empty-state";
import { PageHeader, Panel, PanelHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { useMe } from "@/lib/auth/hooks";
import { canManageUsers, type Role, ROLE_DESCRIPTIONS, ROLE_LABELS, ROLES } from "@/lib/auth/permissions";
import { formatDateTime } from "@/lib/format";
import { useCreateUser, useUpdateUser, useUsers, type User } from "@/lib/users/hooks";

const ROLE_BADGE: Record<Role, string> = {
  admin: "bg-primary/10 text-primary dark:bg-primary/15",
  senior_reviewer: "bg-warning/10 text-warning dark:bg-warning/15",
  analyst: "bg-secondary text-secondary-foreground",
};

export function UsersView() {
  const { data: me } = useMe();
  const users = useUsers();
  const [adding, setAdding] = useState(false);

  if (me && !canManageUsers(me.role)) {
    return (
      <>
        <PageHeader title="Users" />
        <EmptyState
          icon={ShieldOff}
          title="Administrators only"
          description="Onboarding and roles are managed by an administrator. Ask one to change your access."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Users"
        description="Who can sign in and what each person may do. Every change here is recorded in the audit log."
        actions={
          <Button onClick={() => setAdding(true)}>
            <UserPlus data-icon="inline-start" aria-hidden="true" />
            Add user
          </Button>
        }
      />
      <div className="space-y-4">
        <Panel aria-labelledby="users-title">
          <PanelHeader
            title={<span id="users-title">Accounts</span>}
            description="Deactivating an account signs that person out at once. Role changes apply to their next request."
          />
          {users.isPending ? (
            <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading users">
              {Array.from({ length: 3 }, (_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : users.isError ? (
            <div className="px-4 py-10">
              <StateMessage
                error={
                  users.error instanceof ApiError && users.error.status === 403
                    ? "Only administrators can see the user list."
                    : getErrorMessage(users.error)
                }
                onRetry={() => users.refetch()}
              />
            </div>
          ) : users.data.length === 0 ? (
            <div className="px-4 py-10">
              <StateMessage emptyIcon={UsersRound} emptyTitle="No users yet" />
            </div>
          ) : (
            <Table aria-labelledby="users-title">
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Added</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.data.map((user) => (
                  <UserRow key={user.id} user={user} isSelf={user.username === me?.username} />
                ))}
              </TableBody>
            </Table>
          )}
        </Panel>
        <Panel className="px-4 py-3">
          <h2 className="text-xs font-semibold text-muted-foreground">What each role can do</h2>
          <dl className="mt-2 grid gap-x-6 gap-y-2.5 md:grid-cols-3">
            {ROLES.map((role) => (
              <div key={role}>
                <dt className="text-[13px] font-medium">{ROLE_LABELS[role]}</dt>
                <dd className="text-[13px] leading-5 text-pretty text-muted-foreground">{ROLE_DESCRIPTIONS[role]}</dd>
              </div>
            ))}
          </dl>
        </Panel>
      </div>
      <AddUserDialog open={adding} onOpenChange={setAdding} />
    </>
  );
}

function UserRow({ user, isSelf }: { user: User; isSelf: boolean }) {
  const update = useUpdateUser();
  const act = (patch: Parameters<typeof update.mutate>[0], done: string) =>
    update.mutate(patch, {
      onSuccess: () => toast.success(done),
      onError: (error) => toast.error(getErrorMessage(error)),
    });

  return (
    <TableRow className={user.is_active ? undefined : "text-muted-foreground"}>
      <TableCell>
        <div className="font-medium">{user.display_name}</div>
        <div className="text-xs text-muted-foreground">
          {user.username}
          {isSelf && " (you)"}
        </div>
      </TableCell>
      <TableCell>
        <Select
          value={user.role}
          disabled={isSelf || !user.is_active || update.isPending}
          onValueChange={(role) => act({ id: user.id, role: role as Role }, `${user.display_name} is now ${ROLE_LABELS[role as Role].toLowerCase()}`)}
        >
          <SelectTrigger size="sm" aria-label={`Role of ${user.display_name}`} className="min-w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent position="popper" align="start">
            {ROLES.map((role) => (
              <SelectItem key={role} value={role}>
                {ROLE_LABELS[role]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell>
        <Badge variant="outline" className={user.is_active ? ROLE_BADGE[user.role] : "border-border"}>
          {user.is_active ? "Active" : "Deactivated"}
        </Badge>
      </TableCell>
      <TableCell className="num text-muted-foreground">
        {formatDateTime(user.created_at)}
        {user.created_by && <span className="block text-xs">by {user.created_by}</span>}
      </TableCell>
      <TableCell className="text-right">
        <Button
          variant={user.is_active ? "outline" : "secondary"}
          size="sm"
          disabled={isSelf || update.isPending}
          onClick={() =>
            act(
              { id: user.id, is_active: !user.is_active },
              user.is_active ? `${user.display_name} deactivated` : `${user.display_name} reactivated`,
            )
          }
        >
          {user.is_active ? "Deactivate" : "Reactivate"}
        </Button>
      </TableCell>
    </TableRow>
  );
}

function AddUserDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const create = useCreateUser();
  const ids = { username: useId(), name: useId(), role: useId(), password: useId() };
  const [form, setForm] = useState({ username: "", display_name: "", role: "analyst" as Role, password: "" });
  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const submit = () =>
    create.mutate(
      { ...form, username: form.username.trim().toLowerCase(), display_name: form.display_name.trim() },
      {
        onSuccess: (user) => {
          toast.success(`${user.display_name} can sign in as ${ROLE_LABELS[user.role].toLowerCase()}`);
          setForm({ username: "", display_name: "", role: "analyst", password: "" });
          onOpenChange(false);
        },
        onError: (error) => toast.error(getErrorMessage(error)),
      },
    );

  return (
    <Dialog open={open} onOpenChange={(next) => !create.isPending && onOpenChange(next)}>
      <DialogContent className="sm:max-w-md">
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <DialogHeader>
            <DialogTitle>Add user</DialogTitle>
            <DialogDescription>
              Create an account and tell the person their username and password yourself; nothing is emailed.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor={ids.name} className="text-[13px]">
              Full name
            </Label>
            <Input id={ids.name} required maxLength={120} value={form.display_name} onChange={(e) => set("display_name")(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={ids.username} className="text-[13px]">
              Username
            </Label>
            <Input
              id={ids.username}
              required
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              pattern="[a-z0-9][a-z0-9._-]{1,99}"
              title="Lowercase letters, digits, dots, dashes and underscores"
              value={form.username}
              onChange={(e) => set("username")(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={ids.role} className="text-[13px]">
              Role
            </Label>
            <Select value={form.role} onValueChange={(v) => set("role")(v)}>
              <SelectTrigger id={ids.role} className="w-full bg-card">
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper" align="start">
                {ROLES.map((role) => (
                  <SelectItem key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{ROLE_DESCRIPTIONS[form.role]}</p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={ids.password} className="text-[13px]">
              Temporary password
            </Label>
            <Input
              id={ids.password}
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => set("password")(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">At least 8 characters.</p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={create.isPending} onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending && <LoaderCircle className="animate-spin" data-icon="inline-start" aria-hidden="true" />}
              Add user
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
