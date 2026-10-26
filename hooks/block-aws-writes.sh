#!/usr/bin/env bash
# Blocks agent shell commands that mutate AWS resources via the AWS CLI.
# All IAM roles are treated as read-only for agent-driven aws invocations.
set -euo pipefail

input="$(cat)"
command="$(echo "$input" | jq -r '.command // empty')"

deny() {
  local reason="$1"
  jq -n \
    --arg cmd "$command" \
    --arg reason "$reason" \
    '{
      "permission": "deny",
      "user_message": $reason,
      "agent_message": ("Command blocked by ~/.cursor/hooks/block-aws-writes.sh: " + $cmd)
    }'
  exit 0
}

AWS_TOKEN_RE='(^|[[:space:];&|'"'"'"])aws([[:space:]]|--|$)'
SAML2AWS_TOKEN_RE='(^|[[:space:];&|'"'"'"])saml2aws([[:space:]]|$)'

has_aws_token() {
  [[ "$command" =~ $AWS_TOKEN_RE ]]
}

has_saml2aws_token() {
  [[ "$command" =~ $SAML2AWS_TOKEN_RE ]]
}

if ! has_aws_token; then
  if has_saml2aws_token || [[ "$command" != *aws* && "$command" != *saml2aws* ]]; then
    echo '{"permission": "allow"}'
    exit 0
  fi
  echo '{"permission": "allow"}'
  exit 0
fi

segments=("$command")

is_read_operation() {
  local op="$1"
  local op_lower
  op_lower="$(printf '%s' "$op" | tr '[:upper:]' '[:lower:]')"
  case "$op_lower" in
    describe*|list*|get*|head*|lookup*|filter*|search*|estimate*|preview*|check*|validate*|test*|wait*|help*|select*|scan*|query*|batch-get*|decode*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_write_operation() {
  local op="$1"
  local op_lower
  op_lower="$(printf '%s' "$op" | tr '[:upper:]' '[:lower:]')"
  case "$op_lower" in
    put*|create*|delete*|update*|modify*|remove*|terminate*|attach*|detach*|register*|start*|stop*|invoke*|run*|enable*|disable*|add*|insert*|upload*|authorize*|revoke*|grant*|cancel*|abort*|restore*|reboot*|rebuild*|replace*|publish*|submit*|send*|associate*|disassociate*|deregister*|unregister*|untag*|tag-resource*|copy-snapshot*|restore*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# Last non-flag positional argument (rough tokenization).
last_positional() {
  local rest="$1"
  local last=""
  local tok
  for tok in $rest; do
    case "$tok" in
      -*) continue ;;
      --) break ;;
      *) last="$tok" ;;
    esac
  done
  printf '%s' "$last"
}

has_s3_source() {
  local rest="$1"
  [[ "$rest" == *s3://* ]]
}

check_s3_cp_or_sync() {
  local rest="$1"
  local last
  last="$(last_positional "$rest")"
  if [[ "$last" == s3://* ]]; then
    deny "Blocked: aws s3 cp/sync to s3:// is a write. Run manually outside the agent."
  fi
  if has_s3_source "$rest" && [[ -n "$last" && "$last" != s3://* ]]; then
    return 0
  fi
  deny "Blocked: aws s3 cp/sync must be a download (s3:// source to local path) or run manually."
}

extract_aws_tail() {
  local segment="$1"
  local cleaned="${segment//saml2aws/__SAML2AWS__}"
  if [[ "$cleaned" =~ (^|[[:space:];&|'"'"'"])aws[[:space:]]+(.*) ]]; then
    printf '%s' "${BASH_REMATCH[2]}"
    return 0
  fi
  return 1
}

check_aws_segment() {
  local segment="$1"
  if [[ ! "$segment" =~ $AWS_TOKEN_RE ]]; then
    return 0
  fi

  local aws_tail
  if ! aws_tail="$(extract_aws_tail "$segment")"; then
    deny "Blocked: could not parse aws command (read-only policy). Run manually."
  fi
  aws_tail="$(printf '%s' "$aws_tail" | sed 's/^[[:space:]]*//')"

  while [[ -n "$aws_tail" ]]; do
    case "$aws_tail" in
      --profile\ *|--region\ *|--output\ *|--query\ *|--filter\ *|--endpoint-url\ *)
        aws_tail="${aws_tail#* }"
        aws_tail="$(printf '%s' "$aws_tail" | sed 's/^[[:space:]]*//')"
        continue
        ;;
      --profile=*|--region=*|--output=*|--query=*|--filter=*|--endpoint-url=*)
        aws_tail="${aws_tail#--*}"
        aws_tail="$(printf '%s' "$aws_tail" | sed 's/^[^[:space:]]*[[:space:]]*//;s/^[[:space:]]*//')"
        continue
        ;;
      -[a-zA-Z]\ *|-[a-zA-Z][[:space:]]*)
        aws_tail="${aws_tail#-?}"
        aws_tail="$(printf '%s' "$aws_tail" | sed 's/^[[:space:]]*//')"
        continue
        ;;
      -[a-zA-Z]*)
        aws_tail="${aws_tail#-?}"
        aws_tail="$(printf '%s' "$aws_tail" | sed 's/^[[:space:]]*//')"
        continue
        ;;
    esac
    break
  done

  local service op
  service="$(printf '%s' "$aws_tail" | awk '{print $1}')"
  op="$(printf '%s' "$aws_tail" | awk '{print $2}')"

  case "$service" in
    configure|history)
      return 0
      ;;
    eks)
      if [[ "$op" == update-kubeconfig ]]; then
        return 0
      fi
      ;;
    s3)
      case "$op" in
        ls)
          return 0
          ;;
        rm|rb|mb|mv|website|presign)
          deny "Blocked: mutating aws s3 command ($op). Run manually outside the agent."
          ;;
        cp|sync)
          check_s3_cp_or_sync "$aws_tail"
          return 0
          ;;
        "")
          deny "Blocked: incomplete aws s3 command. Run manually outside the agent."
          ;;
        *)
          deny "Blocked: aws s3 $op is not allowed (read-only policy). Run manually."
          ;;
      esac
      ;;
    "")
      deny "Blocked: incomplete aws command. Run manually outside the agent."
      ;;
  esac

  if [[ -z "$op" ]]; then
    deny "Blocked: could not classify aws $service operation (read-only policy). Run manually."
  fi

  if is_write_operation "$op"; then
    deny "Blocked: aws $service $op is a mutating operation. Run manually outside the agent."
  fi

  if is_read_operation "$op"; then
    return 0
  fi

  deny "Blocked: aws $service $op is not on the read-only allowlist. Run manually outside the agent."
}

for seg in "${segments[@]}"; do
  check_aws_segment "$seg"
done

echo '{"permission": "allow"}'
