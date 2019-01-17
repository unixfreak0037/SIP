import uuid

from flask import jsonify, request, url_for
from sqlalchemy import exc

from project import db
from project.api import bp
from project.api.decorators import check_apikey
from project.api.errors import error_response
from project.api.helpers import parse_boolean
from project.models import Campaign, Event, EventAttackVector, EventDisposition, EventPreventionTool, \
    EventRemediation, EventStatus, EventType, IntelReference, IntelSource, Malware, Tag, User

"""
CREATE
"""


@bp.route('/events', methods=['POST'])
@check_apikey
def create_event():
    """ Creates a new event. """

    data = request.values or {}

    # Verify the required fields (name) are present.
    if 'name' not in data:
        return error_response(400, 'Request must include: name')

    # Verify this name does not already exist.
    existing = Event.query.filter_by(name=data['name']).first()
    if existing:
        return error_response(409, 'Event name already exists')

    # Verify the disposition (has default).
    if 'disposition' not in data:
        disposition = EventDisposition.query.order_by(EventDisposition.id).limit(1).first()
    else:
        disposition = EventDisposition.query.filter_by(value=data['disposition']).first()
        if not disposition:
            return error_response(404, 'Event disposition not found: {}'.format(data['disposition']))

    # Verify the status (has default).
    if 'status' not in data:
        status = EventStatus.query.order_by(EventStatus.id).limit(1).first()
    else:
        status = EventStatus.query.filter_by(value=data['status']).first()
        if not status:
            return error_response(404, 'Event status not found: {}'.format(data['status']))

    # Create the event object.
    event = Event(name=data['name'], disposition=disposition, status=status)

    # Verify any attack vectors that were specified.
    for value in data.getlist('attack_vectors'):
        attack_vector = EventAttackVector.query.filter_by(value=value).first()
        if not attack_vector:
            error_response(404, 'Attack vector not found: {}'.format(value))
        event.attack_vectors.append(attack_vector)

    # Verify campaign if one was specified.
    if 'campaign' in data:
        campaign = Campaign.query.filter_by(name=data['campaign'])
        if not campaign:
            return error_response(404, 'Campaign not found: {}'.format(data['campaign']))
        event.campaign = campaign

    # Verify any malware that was specified.
    for value in data.getlist('malware'):
        malware = Malware.query.filter_by(name=value).first()
        if not malware:
            return error_response(404, 'Malware not found: {}'.format(value))
        event.malware.append(malware)

    # Verify any prevention tools that were specified.
    for value in data.getlist('prevention_tools'):
        prevention_tool = EventPreventionTool.query.filter_by(value=value).first()
        if not prevention_tool:
            return error_response(404, 'Prevention tool not found: {}'.format(value))
        event.prevention_tools.append(prevention_tool)

    # Verify any references that were specified.
    for value in data.getlist('references'):
        reference = IntelReference.query.filter_by(reference=value).first()
        if not reference:
            return error_response(404, 'Reference not found: {}'.format(value))
        event.references.append(reference)

    # Verify any remediations that were specified.
    for value in data.getlist('remediations'):
        remediation = EventRemediation.query.filter_by(value=value).first()
        if not remediation:
            return error_response(404, 'Remediation not found: {}'.format(value))
        event.remediations.append(remediation)

    # Verify any tags that were specified.
    for value in data.getlist('tags'):
        tag = Tag.query.filter_by(value=value).first()
        if not tag:
            return error_response(404, 'Tag not found: {}'.format(value))
        event.tags.append(tag)

    # Verify any types that were specified.
    for value in data.getlist('types'):
        _type = EventType.query.filter_by(value=value).first()
        if not _type:
            return error_response(404, 'Type not found: {}'.format(value))
        event.types.append(_type)

    # Save the event.
    db.session.add(event)
    db.session.commit()

    response = jsonify(event.to_dict())
    response.status_code = 201
    response.headers['Location'] = url_for('api.read_event', event_id=event.id)
    return response


"""
READ
"""


@bp.route('/events/<int:event_id>', methods=['GET'])
@check_apikey
def read_event(event_id):
    """ Gets a single event given its ID. """

    event = Event.query.get(event_id)
    if not event:
        return error_response(404, 'Event ID not found')

    return jsonify(event.to_dict())


@bp.route('/events', methods=['GET'])
@check_apikey
def read_events():
    """ Gets a paginated list of events based on various filter criteria. """

    filters = set()

    # Attack vector filter
    if 'attack_vectors' in request.args:
        attack_vectors = request.args.get('attack_vectors').split(',')
        for attack_vector in attack_vectors:
            filters.add(Event.attack_vectors.any(value=attack_vector))

    # Campaign filter
    if 'campaign' in request.args:
        campaign = request.args.get('campaign')
        filters.add(Event.campaign.name == campaign)

    # Disposition filter
    if 'disposition' in request.args:
        disposition = request.args.get('disposition')
        filters.add(Event.disposition.value == disposition)

    # Malware filter
    if 'malware' in request.args:
        malware = request.args.get('malware').split(',')
        for m in malware:
            filters.add(Event.malware.any(name=m))

    # Name filter
    if 'name' in request.args:
        filters.add(Event.name.like('%{}%'.format(request.args.get('name'))))

    # Prevention tool filter
    if 'prevention_tools' in request.args:
        prevention_tools = request.args.get('prevention_tools').split(',')
        for prevention_tool in prevention_tools:
            filters.add(Event.prevention_tools.any(value=prevention_tool))

    # Source filter (IntelReference)
    if 'source' in request.args:
        source = IntelSource.query.filter_by(value=request.args.get('source')).first()
        if source:
            source_id = source.id
        else:
            source_id = -1
        filters.add(Event.references.any(_intel_source_id=source_id))

    # Status filter
    if 'status' in request.args:
        status = request.args.get('status')
        filters.add(Event.status.value == status)

    # Tags filter
    if 'tags' in request.args:
        tags = request.args.get('tags').split(',')
        for tag in tags:
            filters.add(Event.tags.any(value=tag))

    # Types filter
    if 'types' in request.args:
        types = request.args.get('types').split(',')
        for _type in types:
            filters.add(Event.types.any(value=_type))

    # Username filter (IntelReference)
    if 'username' in request.args:
        user = User.query.filter_by(username=request.args.get('username')).first()
        if user:
            user_id = user.id
        else:
            user_id = -1
        filters.add(Event.references.any(_user_id=user_id))

    data = Event.to_collection_dict(Event.query.filter(*filters), 'api.read_events', **request.args)
    return jsonify(data)


"""
UPDATE
"""


@bp.route('/events/<int:event_id>', methods=['PUT'])
@check_apikey
def update_event(event_id):
    """ Updates an existing event. """

    data = request.values or {}

    # Verify the ID exists.
    event = Event.query.get(event_id)
    if not event:
        return error_response(404, 'Event ID not found')

    # Verify active if it was specified. Defaults to False.
    if 'active' in data:
        event.active = parse_boolean(data['active'], default=False)

    # Verify apikey if it was specified. Defaults to True.
    if 'apikey_refresh' in data:
        if parse_boolean(data['apikey_refresh'], default=True):
            event.apikey = uuid.uuid4()

    # Verify email if one was specified.
    if 'email' in data:

        # Verify this email does not already exist.
        existing = Event.query.filter_by(email=data['email']).first()
        if existing:
            return error_response(409, 'Event email already exists')
        else:
            event.email = data['email']

    # Verify first_name if one was specified.
    if 'first_name' in data:
        event.first_name = data['first_name']

    # Verify last_name if one was specified.
    if 'last_name' in data:
        event.last_name = data['last_name']

    # Verify password if one was specified.
    if 'password' in data:
        event.password = hash_password(data['password'])

    # Verify roles if any were specified.
    roles = data.getlist('roles')
    valid_roles = []
    for role in roles:

        # Verify each role is actually valid.
        r = Role.query.filter_by(name=role).first()
        if not r:
            results = Role.query.all()
            acceptable = sorted([r.name for r in results])
            return error_response(400, 'Valid roles: {}'.format(', '.join(acceptable)))
        valid_roles.append(r)
    if valid_roles:
        event.roles = valid_roles

    # Verify eventname if one was specified.
    if 'eventname' in data:

        # Verify this eventname does not already exist.
        existing = Event.query.filter_by(eventname=data['eventname']).first()
        if existing:
            return error_response(409, 'Event eventname already exists')
        else:
            event.eventname = data['eventname']

    db.session.commit()

    # Add the event's API key to the response.
    event_dict = event.to_dict()
    event_dict['apikey'] = event.apikey
    response = jsonify(event_dict)
    return response


"""
DELETE
"""


@bp.route('/events/<int:event_id>', methods=['DELETE'])
@check_apikey
def delete_event(event_id):
    """ Deletes an event. """

    event = Event.query.get(event_id)
    if not event:
        return error_response(404, 'Event ID not found')

    try:
        db.session.delete(event)
        db.session.commit()
    except exc.IntegrityError:
        db.session.rollback()
        return error_response(409, 'Unable to delete event due to foreign key constraints')

    return '', 204