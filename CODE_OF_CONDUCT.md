# Code of Conduct

## Why this exists

This project is a security tool. People bring it problems when something is
already going wrong on a server they are responsible for, often under time
pressure, often having to admit in public that they misconfigured something.
That only works if asking here is safe. This document says what that means in
practice.

It applies to everyone - maintainers included - in every space the project
uses: issues, pull requests, discussions, commit messages, code review, the
security advisory process and any private correspondence that starts in one of
them.

## What we expect

- **Assume the other person is competent and acting in good faith.** Someone
  reporting a false positive has usually already checked the obvious things.
- **Review the change, not the person.** "This will break waivers when the
  finding is not actionable" is useful. "Did you even read the code?" is not.
- **Say what you want changed and why.** A review comment that leaves the
  author guessing costs another round trip for everyone.
- **Accept that not every change will be merged.** A maintainer declining a
  feature is not a judgement about you, and asking for the reasoning is fine.
- **Respect an operator's environment.** People run this in circumstances you
  do not know about - air-gapped networks, ancient distributions, policies they
  cannot change. "Just upgrade" is rarely the whole answer.
- **Be careful with other people's data.** See
  [Instance data](#instance-data) below.

## What is not acceptable

- Harassment, in public or private. Insults, slurs, or attacks based on age,
  body size, disability, ethnicity, gender identity or expression, level of
  experience, nationality, personal appearance, race, religion, sexual
  identity or orientation, or anything comparable.
- Sexualised language or imagery, and unwelcome sexual attention.
- Publishing anyone's private information - a real name, an address, an email
  address, an employer, a hostname or an IP address - without their explicit
  permission.
- Sustained disruption: derailing threads, reopening settled decisions to wear
  people down, or demanding unpaid work from volunteers.
- Deliberately encouraging any of the above.

## Instance data

Specific to this project, and taken as seriously as anything else here:

**Never post credentials, tokens, cookies, session identifiers or the hostname
or IP address of a production instance.** Not in an issue, not in a pull
request, not in a log excerpt, not in a screenshot. Use
`opencloud.example.com` and placeholder secrets - the maintainers do the same
throughout the codebase and its tests.

If you see such data in a thread, do not quote it in your reply. Report it
using the process below and it will be removed. Note that anything published
publicly should be considered compromised: rotate the token, do not merely
delete the comment.

**Do not scan an instance you are not responsible for**, and do not post the
results of having done so. That includes using a public OpenCloud instance as
a convenient test target.

**Vulnerabilities in this tool are not reported here.** Use the private
process in [SECURITY.md](SECURITY.md). Publishing a working exploit against
other people's monitoring hosts before there is a fix is a violation of this
document, regardless of intent.

## Reporting a problem

Report a concern privately to the maintainer via GitHub - open a
[security advisory](https://github.com/sowoi/check-opencloud-security/security/advisories/new)
if it involves data that must not become public, or contact
[@sowoi](https://github.com/sowoi) directly. Do not open a public issue about
someone's conduct.

A report is more useful with links to the messages concerned, and with what
you would like to happen. You do not have to have a proposed outcome.

What to expect:

- An acknowledgement within **five working days**.
- Your identity kept confidential, as far as acting on the report allows. If
  it cannot be, you will be told before anything is done.
- No retaliation for a report made in good faith. Deliberately false reports
  are themselves a violation.

Reports about a maintainer are taken by the other maintainers. Where the
project has a single maintainer and the report concerns them, escalate to
[GitHub Support](https://support.github.com/contact/report-abuse), which can
act independently of this repository.

## What happens next

Maintainers are responsible for enforcing this document and will explain their
reasoning when they act. Responses are proportionate and escalate only when
they need to:

1. **A correction.** A private note explaining what was wrong and why, and
   what to do instead. Most things end here.
2. **A warning.** A stated consequence for continuing, and no interaction with
   the people involved - including unsolicited contact with anyone enforcing
   this document - for a set period.
3. **A temporary ban** from all project spaces.
4. **A permanent ban.**

Editing or deleting a comment that contains credentials, personal data or a
production hostname is not a sanction. It happens immediately, and the author
is told afterwards.

If you think a decision was wrong, say so to the maintainers. That is not
itself a violation of anything.

## Scope

This applies in all project spaces, and when you are representing the project
elsewhere - posting from an official account, or speaking as a contributor at
an event.

It does not give the maintainers authority over your conduct in unrelated
places. It does mean that behaviour elsewhere may be considered when it
creates a credible risk to people here.

## Attribution

Written for this project, drawing on the structure and the enforcement ladder
of the [Contributor Covenant](https://www.contributor-covenant.org),
version 2.1.
