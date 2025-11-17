#!/usr/bin/env python3
"""
OntServe CLI Commands for User Management
"""
import click
from datetime import datetime, timezone
from flask import Flask
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash
from sqlalchemy import select

from web.models import db, User


@click.command()
@click.option('--username', prompt=True, help='Username for the admin user')
@click.option('--email', prompt=True, help='Email address for the admin user')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True,
              help='Password for the admin user')
@click.option('--first-name', default='', help='First name (optional)')
@click.option('--last-name', default='', help='Last name (optional)')
@click.option('--organization', default='', help='Organization (optional)')
@with_appcontext
def create_admin(username, email, password, first_name, last_name, organization):
    """Create an admin user for OntServe."""
    
    # Check if user already exists
    stmt = select(User).where(
        (User.username == username) | (User.email == email)
    )
    existing_user = db.session.execute(stmt).scalar_one_or_none()

    if existing_user:
        if existing_user.username == username:
            click.echo(f"Error: Username '{username}' already exists")
        else:
            click.echo(f"Error: Email '{email}' already exists")
        return
    
    # Create admin user
    admin_user = User(
        username=username,
        email=email,
        password=password,  # This will be hashed in User.__init__
        first_name=first_name or None,
        last_name=last_name or None,
        organization=organization or None,
        is_admin=True,
        is_active=True,
        can_import_ontologies=True,
        can_edit_ontologies=True,
        can_delete_ontologies=True,
        can_publish_versions=True,
        can_access_api=True
    )
    
    db.session.add(admin_user)
    db.session.commit()
    
    click.echo(f"✅ Admin user '{username}' created successfully!")
    click.echo(f"   Email: {email}")
    click.echo(f"   Full name: {admin_user.get_full_name()}")
    if organization:
        click.echo(f"   Organization: {organization}")


@click.command()
@click.option('--username', prompt=True, help='Username for the regular user')
@click.option('--email', prompt=True, help='Email address for the user')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True,
              help='Password for the user')
@click.option('--first-name', default='', help='First name (optional)')
@click.option('--last-name', default='', help='Last name (optional)')
@click.option('--organization', default='', help='Organization (optional)')
@click.option('--can-import/--no-import', default=True, help='Can import ontologies (default: yes)')
@click.option('--can-edit/--no-edit', default=True, help='Can edit ontologies (default: yes)')
@click.option('--can-delete/--no-delete', default=False, help='Can delete ontologies (default: no)')
@click.option('--can-publish/--no-publish', default=True, help='Can publish versions (default: yes)')
@click.option('--can-api/--no-api', default=True, help='Can access API (default: yes)')
@with_appcontext
def create_user(username, email, password, first_name, last_name, organization,
                can_import, can_edit, can_delete, can_publish, can_api):
    """Create a regular user for OntServe."""
    
    # Check if user already exists
    stmt = select(User).where(
        (User.username == username) | (User.email == email)
    )
    existing_user = db.session.execute(stmt).scalar_one_or_none()

    if existing_user:
        if existing_user.username == username:
            click.echo(f"Error: Username '{username}' already exists")
        else:
            click.echo(f"Error: Email '{email}' already exists")
        return
    
    # Create regular user
    user = User(
        username=username,
        email=email,
        password=password,  # This will be hashed in User.__init__
        first_name=first_name or None,
        last_name=last_name or None,
        organization=organization or None,
        is_admin=False,
        is_active=True,
        can_import_ontologies=can_import,
        can_edit_ontologies=can_edit,
        can_delete_ontologies=can_delete,
        can_publish_versions=can_publish,
        can_access_api=can_api
    )
    
    db.session.add(user)
    db.session.commit()
    
    click.echo(f"✅ User '{username}' created successfully!")
    click.echo(f"   Email: {email}")
    click.echo(f"   Full name: {user.get_full_name()}")
    if organization:
        click.echo(f"   Organization: {organization}")
    click.echo("   Permissions:")
    click.echo(f"   - Import ontologies: {'✓' if can_import else '✗'}")
    click.echo(f"   - Edit ontologies: {'✓' if can_edit else '✗'}")
    click.echo(f"   - Delete ontologies: {'✓' if can_delete else '✗'}")
    click.echo(f"   - Publish versions: {'✓' if can_publish else '✗'}")
    click.echo(f"   - API access: {'✓' if can_api else '✗'}")


@click.command()
@with_appcontext
def list_users():
    """List all users in the system."""
    stmt = select(User).order_by(User.username)
    users = db.session.execute(stmt).scalars().all()

    if not users:
        click.echo("No users found.")
        return
    
    click.echo(f"Found {len(users)} user(s):")
    click.echo()
    
    for user in users:
        status_badges = []
        if user.is_admin:
            status_badges.append("ADMIN")
        if not user.is_active:
            status_badges.append("INACTIVE")
        
        status = f" [{', '.join(status_badges)}]" if status_badges else ""
        click.echo(f"• {user.username}{status}")
        click.echo(f"  Email: {user.email}")
        click.echo(f"  Full name: {user.get_full_name()}")
        if user.organization:
            click.echo(f"  Organization: {user.organization}")
        click.echo(f"  Created: {user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else 'Unknown'}")
        if user.last_login:
            click.echo(f"  Last login: {user.last_login.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not user.is_admin:
            permissions = []
            if user.can_import_ontologies:
                permissions.append("import")
            if user.can_edit_ontologies:
                permissions.append("edit")
            if user.can_delete_ontologies:
                permissions.append("delete")
            if user.can_publish_versions:
                permissions.append("publish")
            if user.can_access_api:
                permissions.append("api")
            click.echo(f"  Permissions: {', '.join(permissions) if permissions else 'none'}")
        
        click.echo()


@click.command()
@click.option('--username', prompt=True, help='Username to delete')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
@with_appcontext
def delete_user(username, confirm):
    """Delete a user from the system."""
    stmt = select(User).where(User.username == username)
    user = db.session.execute(stmt).scalar_one_or_none()

    if not user:
        click.echo(f"Error: User '{username}' not found")
        return
    
    if not confirm:
        click.echo(f"User to delete: {user.username} ({user.email})")
        if user.is_admin:
            click.echo("⚠️  WARNING: This is an admin user!")
        
        if not click.confirm("Are you sure you want to delete this user?"):
            click.echo("Operation cancelled.")
            return
    
    db.session.delete(user)
    db.session.commit()
    
    click.echo(f"✅ User '{username}' deleted successfully!")


def init_cli(app):
    """Initialize CLI commands with the Flask app."""
    app.cli.add_command(create_admin)
    app.cli.add_command(create_user)
    app.cli.add_command(list_users)
    app.cli.add_command(delete_user)